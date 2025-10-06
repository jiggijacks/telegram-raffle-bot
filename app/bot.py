import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base, RaffleEntry
import aiohttp

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///raffle.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")

# Setup bot
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Setup Database
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Create tables
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized.")

# --- COMMAND HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    welcome_text = (
        "🎉 <b>Welcome to MegaWin Raffle Bot!</b>\n\n"
        "Buy tickets and stand a chance to win daily prizes! 💰\n\n"
        "Here are some commands to get started:\n"
        "/buy - Purchase a raffle ticket 🎟️\n"
        "/ticket - Check your current ticket 🎫\n"
        "/help - Get help information ℹ️"
    )
    await message.answer(welcome_text)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "🧭 <b>How to Use MegaWin Raffle Bot</b>\n\n"
        "1️⃣ Use /buy to purchase your ticket via Paystack.\n"
        "2️⃣ Use /ticket to view your ticket details.\n"
        "3️⃣ Winners are selected daily at midnight! 🌙\n\n"
        "Commands:\n"
        "/start - Restart the bot\n"
        "/buy - Purchase a ticket\n"
        "/ticket - Check your ticket\n"
    )
    await message.answer(help_text)


@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    async with aiohttp.ClientSession() as session:
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "email": f"user_{message.from_user.id}@megawinraffle.com",
            "amount": 1000 * 100,  # 1000 NGN
            "callback_url": "https://megawinraffle.com/verify",  # placeholder
        }
        async with session.post(url, headers=headers, json=data) as resp:
            res = await resp.json()
            if res.get("status"):
                pay_url = res["data"]["authorization_url"]
                await message.answer(
                    f"💳 Click below to complete your payment:\n\n<a href='{pay_url}'>Pay with Paystack</a>",
                    disable_web_page_preview=True,
                )
            else:
                await message.answer("❌ Payment initialization failed. Please try again later.")


@dp.message(Command(commands=["ticket", "tickets"]))
async def cmd_ticket(message: Message):
    async with async_session() as session:
        result = await session.execute(
            RaffleEntry.__table__.select().where(RaffleEntry.user_id == message.from_user.id)
        )
        ticket = result.scalar_one_or_none()

        if ticket:
            await message.answer(
                f"🎫 You have an active ticket!\n\nTicket ID: <b>{ticket.id}</b>\n"
                f"Purchased on: <b>{ticket.timestamp.strftime('%Y-%m-%d')}</b>"
            )
        else:
            await message.answer("🚫 You don't have any active tickets.\nUse /buy to get one!")


@dp.message(Command("winners"))
async def cmd_winners(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("🚫 This command is only available to the admin.")

    async with async_session() as session:
        result = await session.execute(RaffleEntry.__table__.select())
        entries = result.scalars().all()

        if not entries:
            await message.answer("📭 No entries found for today.")
            return

        import random
        winner = random.choice(entries)
        await message.answer(
            f"🏆 <b>Daily Winner:</b>\n\n"
            f"User ID: <code>{winner.user_id}</code>\n"
            f"Ticket ID: <b>{winner.id}</b>\n\n🎉 Congratulations!"
        )


# --- MAIN ---
async def main():
    await on_startup()
    logger.info("🎯 Starting MegaWin Raffle Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
