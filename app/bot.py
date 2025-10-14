import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from dotenv import load_dotenv
import aiohttp
import random
from aiogram.filters import Command  # Import Command filter from aiogram.filters

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()  # Load environment variables from .env file

BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///raffle.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-railway-app-url.up.railway.app/webhook/paystack")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")

# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Initialize Telegram Bot + FastAPI
# -----------------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

app = FastAPI()

# -----------------------------
# Database Setup
# -----------------------------
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base, RaffleEntry

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database initialized successfully.")

# -----------------------------
# Telegram Commands
# -----------------------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = (
        "🎉 <b>Welcome to MegaWin Raffle Bot!</b>\n\n"
        "Buy tickets and stand a chance to win daily prizes! 💰\n\n"
        "Commands:\n"
        "/buy - Purchase a raffle ticket 🎟️\n"
        "/ticket - Check your ticket 🎫\n"
        "/help - Get help info ℹ️"
    )
    await message.answer(welcome_text)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🧭 <b>How to Use MegaWin Raffle Bot</b>\n\n"
        "1️⃣ Use /buy to purchase your ticket via Paystack.\n"
        "2️⃣ Use /ticket to view your ticket details.\n"
        "3️⃣ Winners are selected daily by the admin.\n\n"
        "Commands:\n"
        "/start - Restart bot\n"
        "/buy - Purchase a ticket\n"
        "/ticket - Check your ticket\n"
    )
    await message.answer(help_text)


@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    async with aiohttp.ClientSession() as session:
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "email": f"user_{message.from_user.id}@megawinraffle.com",
            "amount": 500 * 100,  # 500 NGN
            "callback_url": WEBHOOK_URL,
            "metadata": {"user_id": message.from_user.id},
        }
        async with session.post(url, headers=headers, json=data) as resp:
            res = await resp.json()
            if res.get("status"):
                pay_url = res["data"]["authorization_url"]
                await message.answer(
                    f"💳 Click below to complete your payment:\n"
                    f"👉 <a href='{pay_url}'>Pay ₦500 via Paystack</a>\n\n"
                    "Once payment is confirmed, your raffle ticket will be added automatically. ✅",
                    disable_web_page_preview=True,
                )
                logger.info(f"User {message.from_user.id} initialized payment.")
            else:
                await message.answer("❌ Payment initialization failed. Please try again later.")


@dp.message(Command("ticket"))
async def cmd_ticket(message: types.Message):
    async with async_session() as session:
        result = await session.execute(
            RaffleEntry.__table__.select().where(RaffleEntry.user_id == message.from_user.id)
        )
        ticket = result.scalar_one_or_none()

        if ticket:
            await message.answer(
                f"🎫 You have an active ticket!\n\n"
                f"Ticket ID: <b>{ticket.id}</b>\n"
                f"Purchased on: <b>{ticket.timestamp.strftime('%Y-%m-%d')}</b>"
            )
        else:
            await message.answer("🚫 You don't have any active tickets.\nUse /buy to get one!")


@dp.message(Command("winners"))
async def cmd_winners(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("🚫 Only the admin can use this command.")
    async with async_session() as session:
        result = await session.execute(RaffleEntry.__table__.select())
        entries = result.scalars().all()
        if not entries:
            await message.answer("📭 No entries found today.")
            return
        winner = random.choice(entries)
        await message.answer(
            f"🏆 <b>Daily Winner:</b>\n\n"
            f"User ID: <code>{winner.user_id}</code>\n"
            f"Ticket ID: <b>{winner.id}</b>\n\n🎉 Congratulations!"
        )


# -----------------------------
# PAYSTACK WEBHOOK ENDPOINT
# -----------------------------
@app.post("/webhook/paystack")
async def verify_paystack_payment(request: Request):
    payload = await request.json()
    logger.info(f"📩 Paystack Webhook Received: {payload}")

    event = payload.get("event")
    data = payload.get("data", {})

    logger.info(f"Event: {event}, Data: {data}")

    if event == "charge.success" and data.get("status") == "success":
        user_id = data.get("metadata", {}).get("user_id")
        reference = data.get("reference")

        logger.info(f"Payment Data - User ID: {user_id}, Reference: {reference}")

        if not user_id or not reference:
            logger.warning("⚠️ Webhook missing user_id or reference.")
            return {"status": "error"}

        # Verify payment reference with Paystack API
        async with aiohttp.ClientSession() as session:
            url = f"https://api.paystack.co/transaction/verify/{reference}"
            headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
            async with session.get(url, headers=headers) as resp:
                verification_response = await resp.json()
                logger.info(f"Verification Response for reference {reference}: {verification_response}")

                if verification_response.get("status") == "success" and verification_response["data"]["status"] == "success":
                    # Payment verified, proceed with saving the ticket
                    async with async_session() as session:
                        entry = RaffleEntry(user_id=user_id, payment_ref=reference)
                        session.add(entry)
                        await session.commit()

                    # Notify user on Telegram
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text="✅ Payment confirmed! Your raffle ticket has been added. Good luck! 🍀",
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed to message user {user_id}: {e}")
                else:
                    logger.warning(f"Payment reference {reference} verification failed.")

    return {"status": "ok"}


# -----------------------------
# RUN BOT + API TOGETHER (using Webhook)
# -----------------------------
async def on_startup(dp):
    webhook_url = f"https://{WEBHOOK_URL}/webhook/paystack"  # Replace with your production URL
    await bot.set_webhook(webhook_url)

async def main():
    await on_startup(dp)
    logger.info("🎯 Starting MegaWin Raffle Bot...")

    from aiogram import executor
    # In Aiogram v3.x, we directly use FastAPI with a custom webhook dispatcher setup
    await dp.start_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
