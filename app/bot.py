import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Text
from dotenv import load_dotenv
import aiohttp
import random
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base, RaffleEntry
import asyncio

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()  # Load environment variables from .env file

BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///raffle.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://megawinraffle.up.railway.app")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")

# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Initialize Telegram Bot + Dispatcher
# -----------------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# -----------------------------
# Database Setup
# -----------------------------
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database initialized successfully.")

# -----------------------------
# Telegram Commands
# -----------------------------
@dp.message(Text(commands=["start"]))
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


@dp.message(Text(commands=["help"]))
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


@dp.message(Text(commands=["buy"]))
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
            "callback_url": f"{WEBHOOK_URL}/webhook/paystack",  # Live callback URL
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


@dp.message(Text(commands=["ticket"]))
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


@dp.message(Text(commands=["winners"]))
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
# Run Bot (Polling)
# -----------------------------
async def main():
    logger.info("🎯 Starting MegaWin Raffle Bot...")
    # Start Polling for commands
    await dp.start_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
