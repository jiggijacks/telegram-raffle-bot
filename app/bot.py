import os
import logging
import random
import asyncio
import aiohttp
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base, User, RaffleEntry
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
# Initialize Bot, Dispatcher & FastAPI
# -----------------------------
bot = Bot(
    token=BOT_TOKEN,
    default=types.DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()  # ✅ Fixed for Aiogram v3
app = FastAPI()


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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()

    referrer_id = None
    if len(args) > 1:
        referrer_id = args[1]

    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            user = User(id=user_id, referral_count=0)
            session.add(user)
            await session.commit()

        if referrer_id and referrer_id != str(user_id):
            referrer = await session.get(User, int(referrer_id))
            if referrer:
                referrer.referral_count += 1
                await session.commit()
                if referrer.referral_count % 5 == 0:
                    free_ticket = RaffleEntry(user_id=referrer.id, payment_ref="FREE_REFERRAL")
                    session.add(free_ticket)
                    await session.commit()
                    try:
                        await bot.send_message(referrer.id, "🎉 You’ve earned a free raffle ticket for 5 referrals! 🏆")
                    except Exception as e:
                        logger.error(f"❌ Failed to message referrer {referrer.id}: {e}")

    ref_link = f"https://t.me/MegaWinRafflebot?start={user_id}"
    welcome_text = (
        f"🎉 Welcome to MegaWin Raffle Bot!\n\n"
        f"Buy tickets and stand a chance to win daily prizes! 💰\n\n"
        f"Your referral link:\n{ref_link}\n\n"
        f"Commands:\n"
        f"/buy - Purchase a raffle ticket 🎟️\n"
        f"/ticket - Check your ticket 🎫\n"
        f"/referrals - Check your referrals 🔗\n"
        f"/help - Get help info ℹ️"
    )
    await message.answer(welcome_text)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🧭 How to Use MegaWin Raffle Bot\n\n"
        "1️⃣ Use /buy to purchase your ticket via Paystack.\n"
        "2️⃣ Use /ticket to view your ticket details.\n"
        "3️⃣ Refer friends to earn free tickets.\n"
        "4️⃣ Winners are selected daily by the admin.\n\n"
        "Commands:\n"
        "/start - Restart bot\n"
        "/buy - Purchase a ticket\n"
        "/ticket - Check your ticket\n"
        "/referrals - Check your referral bonus"
    )
    await message.answer(help_text)


@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    user_id = message.from_user.id
    reference = f"RAFFLE-{random.randint(100000, 999999)}"

    payment_url = f"https://checkout.paystack.com/{reference}"

    await message.answer(
        f"💳 Click below to complete your ticket purchase:\n\n"
        f"{payment_url}\n\n"
        f"Once payment is confirmed, your raffle ticket will be added automatically ✅"
    )

    # Log the purchase attempt
    logger.info(f"User {user_id} initiated payment with reference {reference}.")


@dp.message(Command("referrals"))
async def cmd_referrals(message: types.Message):
    user_id = message.from_user.id
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user:
            await message.answer(f"👥 You have referred {user.referral_count} users.")
        else:
            await message.answer("You have not referred any users yet. Share your link with friends!")


@dp.message(Command("ticket"))
async def cmd_ticket(message: types.Message):
    user_id = message.from_user.id
    async with async_session() as session:
        result = await session.execute(select(RaffleEntry).filter_by(user_id=user_id))
        tickets = result.scalars().all()
        if tickets:
            ticket_list = "\n".join([f"🎟️ {t.payment_ref}" for t in tickets])
            await message.answer(f"Your tickets:\n{ticket_list}")
        else:
            await message.answer("❌ You have no tickets yet. Use /buy to get one.")


# -----------------------------
# PAYSTACK WEBHOOK ENDPOINT
# -----------------------------
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
        async with aiohttp.ClientSession() as session_http:
            url = f"https://api.paystack.co/transaction/verify/{reference}"
            headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
            async with session_http.get(url, headers=headers) as resp:
                verification_response = await resp.json()
                if (
                    verification_response.get("status") == "success"
                    and verification_response["data"]["status"] == "success"
                ):
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
# RUN BOT + API TOGETHER
# -----------------------------
async def main():
    await on_startup()
    logger.info("🎯 Starting MegaWin Raffle Bot...")

    import uvicorn

    def run_api():
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

    Thread(target=run_api, daemon=True).start()

    # Start Telegram polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
