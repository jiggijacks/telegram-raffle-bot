import os
import logging
import asyncio
import aiohttp
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram import types
from aiogram.types import Message
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base, RaffleEntry
from app.models import User as ModelsUser

# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Environment Variables
# -----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///raffle.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-railway-app-url.up.railway.app/webhook/paystack")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")

# -----------------------------
# Initialize Bot and Dispatcher (correct version)
# -----------------------------
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
app = FastAPI()


# -------------------------------
# Example handler (keep or modify)
# -------------------------------
@dp.message(CommandStart())
async def start_command(message: Message):
    await message.answer("Welcome to the raffle bot! 🎟️")

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer("Use /start to begin and follow the instructions.")


# -------------------------------
# Entry point
# -------------------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


# -------------------------------------------------
# CONFIGURATION
# -------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///raffle.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-railway-app-url.up.railway.app/webhook/paystack")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN not found in environment variables.")

# -------------------------------------------------
# INITIALIZE COMPONENTS
# -------------------------------------------------
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
app = FastAPI()

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# -------------------------------------------------
# STARTUP: INIT DATABASE
# -------------------------------------------------
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database initialized successfully.")

# -------------------------------------------------
# BOT COMMANDS
# -------------------------------------------------
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Handle /start command with optional referral"""
    referrer_id = None
    parts = message.text.strip().split()
    if len(parts) > 1:
        try:
            referrer_id = int(parts[1])
        except ValueError:
            pass

    async with async_session() as session:
        user = await session.get(ModelsUser, {"telegram_id": message.from_user.id})
        if not user:
            new_user = ModelsUser(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                referred_by=referrer_id,
            )
            session.add(new_user)
            await session.commit()

            if referrer_id:
                referrer = await session.get(ModelsUser, {"telegram_id": referrer_id})
                if referrer:
                    referrer.referral_count += 1
                    await session.commit()

    await message.answer(
        f"🎉 Welcome to <b>MegaWin Raffle Bot</b>!\n"
        f"Invite friends with your referral link:\n"
        f"<code>https://t.me/{(await bot.me()).username}?start={message.from_user.id}</code>"
    )

@dp.message(Command("buy"))
async def buy_ticket_handler(message: types.Message):
    """Generate Paystack payment link"""
    amount = 1000 * 100  # NGN 1000
    email = f"user{message.from_user.id}@example.com"

    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
        payload = {
            "email": email,
            "amount": amount,
            "callback_url": WEBHOOK_URL,
        }
        async with session.post("https://api.paystack.co/transaction/initialize", headers=headers, json=payload) as resp:
            data = await resp.json()
            if data.get("status"):
                auth_url = data["data"]["authorization_url"]
                await message.answer(
                    f"💳 Click below to complete your ticket purchase:\n{auth_url}"
                )
            else:
                await message.answer("⚠️ Failed to initialize payment. Please try again later.")

@dp.message(Command("tickets"))
async def my_tickets_handler(message: types.Message):
    """Show user's tickets"""
    async with async_session() as session:
        result = await session.execute(
            RaffleEntry.__table__.select().where(RaffleEntry.user_id == message.from_user.id)
        )
        tickets = result.fetchall()

    if tickets:
        await message.answer(f"🎟 You have {len(tickets)} raffle ticket(s). Good luck!")
    else:
        await message.answer("😕 You don’t have any raffle tickets yet. Use /buy to get one!")

# -------------------------------------------------
# PAYSTACK WEBHOOK
# -------------------------------------------------
@app.post("/webhook/paystack")
async def paystack_webhook(request: Request):
    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success":
        email = data.get("customer", {}).get("email")
        reference = data.get("reference")
        telegram_id = int(email.split("user")[1].split("@")[0])

        async with async_session() as session:
            user = await session.execute(
                ModelsUser.__table__.select().where(ModelsUser.telegram_id == telegram_id)
            )
            user_obj = user.scalar_one_or_none()
            if user_obj:
                new_ticket = RaffleEntry(
                    user_id=user_obj.id,
                    payment_ref=reference,
                    free_ticket=False
                )
                session.add(new_ticket)
                await session.commit()
                await bot.send_message(
                    chat_id=telegram_id,
                    text="🎟 Payment successful! Your raffle ticket has been added. Good luck!"
                )

    return {"status": "ok"}

# -------------------------------------------------
# START BOT
# -------------------------------------------------
async def main():
    await on_startup()
    logger.info("🎯 Starting MegaWin Raffle Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
