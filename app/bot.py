import os
import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.dispatcher.filters import Text
from aiogram.types import Message
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base, RaffleEntry

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///raffle.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# Initialize FastAPI (for webhook)
app = FastAPI()

# Setup Database
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Create tables
async def on_startup(_):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database initialized successfully.")

# --- COMMAND HANDLERS ---

@dp.message_handler(commands=["start"])
async def cmd_start(message: Message):
    text = (
        "🎉 <b>Welcome to MegaWin Raffle Bot!</b>\n\n"
        "Buy tickets and stand a chance to win daily prizes! 💰\n\n"
        "Commands:\n"
        "/buy - Purchase a raffle ticket 🎟️\n"
        "/ticket - Check your ticket 🎫\n"
        "/help - Learn more ℹ️"
    )
    await message.answer(text)


@dp.message_handler(commands=["help"])
async def cmd_help(message: Message):
    text = (
        "🧭 <b>How to use MegaWin Raffle Bot</b>\n\n"
        "1️⃣ Use /buy to purchase your ticket via Paystack.\n"
        "2️⃣ Use /ticket to check your current ticket.\n"
        "3️⃣ Winners are selected daily by the admin!\n\n"
        "Commands:\n"
        "/start - Restart the bot\n"
        "/buy - Buy ticket\n"
        "/ticket - Check ticket\n"
    )
    await message.answer(text)


@dp.message_handler(commands=["buy"])
async def cmd_buy(message: Message):
    async with aiohttp.ClientSession() as session:
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "email": f"user_{message.from_user.id}@megawinraffle.com",
            "amount": 500 * 100,  # 500 NGN
            "callback_url": "https://megawinraffle.com/verify",
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


@dp.message_handler(commands=["ticket"])
@dp.message_handler(Text(equals=["tickets", "my tickets"], ignore_case=True))
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


@dp.message_handler(commands=["winners"])
async def cmd_winners(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("🚫 This command is only for the admin.")

    async with async_session() as session:
        result = await session.execute(RaffleEntry.__table__.select())
        entries = result.scalars().all()

        if not entries:
            return await message.answer("📭 No entries found for today.")

        import random
        winner = random.choice(entries)
        await message.answer(
            f"🏆 <b>Daily Winner:</b>\n\n"
            f"User ID: <code>{winner.user_id}</code>\n"
            f"Ticket ID: <b>{winner.id}</b>\n\n🎉 Congratulations!"
        )


# --- PAYSTACK WEBHOOK ---
@app.post("/webhook/paystack")
async def verify_paystack_payment(request: Request):
    payload = await request.json()
    logger.info(f"📩 Paystack Webhook Received: {payload}")

    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success" and data.get("status") == "success":
        user_id = data.get("metadata", {}).get("user_id")
        reference = data.get("reference")

        if not user_id or not reference:
            logger.warning("⚠️ Webhook missing user_id or reference.")
            return {"status": "error"}

        # Verify payment reference with Paystack API
        async with aiohttp.ClientSession() as session:
            url = f"https://api.paystack.co/transaction/verify/{reference}"
            headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
            async with session.get(url, headers=headers) as resp:
                verification_response = await resp.json()
                if (
                    verification_response.get("status") == "success"
                    and verification_response["data"]["status"] == "success"
                ):
                    async with async_session() as db:
                        entry = RaffleEntry(user_id=user_id, payment_ref=reference)
                        db.add(entry)
                        await db.commit()

                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text="✅ Payment confirmed! Your raffle ticket has been added. 🍀",
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed to notify user {user_id}: {e}")

    return {"status": "ok"}


# --- MAIN ---
async def main():
    await on_startup(None)
    logger.info("🎯 Starting MegaWin Raffle Bot...")
    await asyncio.gather(
        asyncio.create_task(executor.start_polling(dp, skip_updates=True)),
    )


if __name__ == "__main__":
    asyncio.run(main())
