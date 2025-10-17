import os
import logging
import asyncio
import aiohttp
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, Text
from aiogram.enums import ParseMode
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session, RaffleEntry

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")

# Initialize FastAPI app and Telegram bot
app = FastAPI()
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# -------------------------------------------------------
# Telegram Commands
# -------------------------------------------------------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🎉 Welcome to *MegaWin Raffle Bot!*\n\n"
        "Use /buy to purchase a raffle ticket.\n"
        "Use /stats to see total tickets sold.\n"
        "Use /winners to view past winners.",
        parse_mode="Markdown"
    )

@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    user_id = message.from_user.id
    paystack_url = f"https://paystack.com/pay/megawin?user_id={user_id}"
    await message.answer(
        f"💳 Click below to complete your ticket purchase:\n\n👉 {paystack_url}"
    )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    async with async_session() as session:
        result = await session.execute(
            "SELECT COUNT(*) FROM raffle_entries"
        )
        count = result.scalar()
    await message.answer(f"📊 Total raffle tickets sold: {count}")

@dp.message(Command("winners"))
async def cmd_winners(message: Message):
    await message.answer("🏆 Winners will be announced soon! Stay tuned!")

# -------------------------------------------------------
# PAYSTACK WEBHOOK HANDLER
# -------------------------------------------------------
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

                if (verification_response.get("status") == "success" and
                        verification_response["data"]["status"] == "success"):
                    
                    # Add raffle entry
                    async with async_session() as session_db:
                        entry = RaffleEntry(user_id=user_id, payment_ref=reference)
                        session_db.add(entry)
                        await session_db.commit()

                    # Notify user
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text="✅ Payment confirmed! Your raffle ticket has been added. Good luck 🍀"
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed to message user {user_id}: {e}")
                else:
                    logger.warning(f"⚠️ Payment verification failed for {reference}")

    return {"status": "ok"}

# -------------------------------------------------------
# MAIN APP ENTRY POINT
# -------------------------------------------------------
async def main():
    logger.info("✅ Database initialized successfully.")
    logger.info("🎯 Starting MegaWin Raffle Bot...")

    bot_task = asyncio.create_task(dp.start_polling(bot))
    await bot_task

if __name__ == "__main__":
    asyncio.run(main())
