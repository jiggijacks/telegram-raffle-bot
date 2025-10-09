import os
import logging
import asyncio
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base, RaffleEntry
import aiohttp
from aiohttp import web

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///raffle.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
APP_URL = os.getenv("APP_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Database setup
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Create tables
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database initialized successfully.")

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
        "3️⃣ Winners are selected daily. Stay tuned!\n\n"
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

        ref = f"{message.from_user.id}_{int(asyncio.get_event_loop().time())}"

        data = {
            "email": f"user_{message.from_user.id}@megawinraffle.com",
            "amount": 500 * 100,  # ₦500
            "callback_url": f"{APP_URL}/verify?ref={ref}",
            "reference": ref,
        }

        async with session.post(url, headers=headers, json=data) as resp:
            res = await resp.json()

            if res.get("status"):
                pay_url = res["data"]["authorization_url"]
                await message.answer(
                    f"💳 Click below to complete your payment:\n"
                    f"👉 <a href='{pay_url}'>Pay ₦500 via Paystack</a>\n\n"
                    "Once your payment is confirmed, your raffle ticket will be added automatically. ✅",
                    disable_web_page_preview=True,
                )
                logger.info(f"User {message.from_user.id} initialized payment {ref}")
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
                f"🎫 You have an active ticket!\n\n"
                f"Ticket ID: <b>{ticket.id}</b>\n"
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

        winner = random.choice(entries)
        await message.answer(
            f"🏆 <b>Daily Winner:</b>\n\n"
            f"User ID: <code>{winner.user_id}</code>\n"
            f"Ticket ID: <b>{winner.id}</b>\n\n🎉 Congratulations!"
        )

# --- PAYSTACK VERIFICATION ENDPOINT ---

async def verify_payment(request):
    ref = request.query.get("ref")
    if not ref:
        return web.Response(text="Missing payment reference.", status=400)

    verify_url = f"https://api.paystack.co/transaction/verify/{ref}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(verify_url, headers=headers) as resp:
            data = await resp.json()

    if data.get("data", {}).get("status") == "success":
        user_id = int(ref.split("_")[0])
        async with async_session() as db:
            entry = RaffleEntry(user_id=user_id, timestamp=datetime.utcnow())
            db.add(entry)
            await db.commit()

        logger.info(f"✅ Ticket added for user {user_id}")
        return web.Response(text="✅ Payment verified and ticket added!")
    else:
        logger.warning(f"❌ Failed verification for {ref}")
        return web.Response(text="❌ Payment verification failed.", status=400)

# --- MAIN FUNCTION ---

async def main():
    await on_startup()
    logger.info("🎯 Starting MegaWin Raffle Bot...")

    # Run both Telegram polling and web server together
    loop = asyncio.get_event_loop()

    # Telegram polling
    bot_task = loop.create_task(dp.start_polling(bot))

    # Webhook for Paystack callback
    app = web.Application()
    app.router.add_get("/verify", verify_payment)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()

    await bot_task

if __name__ == "__main__":
    asyncio.run(main())
