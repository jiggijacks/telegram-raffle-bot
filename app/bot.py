import os
import asyncio
import logging
import requests
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from app.database import (
    init_db,
    get_or_create_user,
    add_ticket,
    get_user_tickets,
    get_all_participants,
)

# =====================================================
# CONFIG
# =====================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()


# =====================================================
# HANDLERS
# =====================================================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Welcome new users."""
    user = await get_or_create_user(message.from_user.id, message.from_user.full_name)
    text = (
        f"🎉 Welcome <b>{message.from_user.full_name}</b> to <b>MegaWin Raffle!</b>\n\n"
        "Buy tickets to enter today's draw and stand a chance to win amazing prizes! 🏆\n\n"
        "🪙 Each ticket costs ₦500.\n"
        "📅 Winners are announced daily.\n\n"
        "Use /buy to purchase tickets or /tickets to check your entries."
    )
    await message.answer(text)


@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    """Initialize Paystack payment."""
    amount = 500 * 100  # 500 NGN
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "email": f"user{message.from_user.id}@megawinraffle.com",
        "amount": amount,
        "callback_url": "https://your-callback-url.com/verify",
    }

    response = requests.post("https://api.paystack.co/transaction/initialize", json=data, headers=headers)

    if response.status_code == 200:
        auth_url = response.json()["data"]["authorization_url"]
        ref = response.json()["data"]["reference"]
        await message.answer(
            f"💳 Click below to complete your payment:\n👉 <a href='{auth_url}'>Pay ₦500 via Paystack</a>\n\n"
            f"Once paid, your ticket will be automatically added. ✅",
            disable_web_page_preview=True,
        )
        logger.info(f"User {message.from_user.id} initialized payment with ref {ref}")
    else:
        await message.answer("❌ Payment initialization failed. Try again later.")


@dp.message(Command("tickets"))
async def cmd_tickets(message: Message):
    """Show user tickets."""
    user = await get_or_create_user(message.from_user.id, message.from_user.full_name)
    tickets = await get_user_tickets(user.id)
    count = len(tickets)

    if count == 0:
        await message.answer("🎫 You don't have any tickets yet.\nUse /buy to get one!")
    else:
        await message.answer(f"🎟 You currently have <b>{count}</b> tickets in the draw. Good luck! 🍀")


# =====================================================
# DAILY WINNER (AUTO OR ADMIN TRIGGER)
# =====================================================
async def pick_daily_winner():
    """Pick a random winner every 24 hours."""
    from random import choice
    participants = await get_all_participants()
    if not participants:
        logger.info("No participants today.")
        return

    winner = choice(participants)
    winner_id = winner.telegram_id

    try:
        await bot.send_message(
            winner_id,
            "🎉 Congratulations! You've been selected as today's MegaWin Raffle winner! 🏆",
        )
        await bot.send_message(
            ADMIN_ID,
            f"🏁 Daily Winner: {winner.full_name} (@{winner.telegram_id})",
        )
        logger.info(f"Winner selected: {winner.full_name} ({winner.telegram_id})")
    except Exception as e:
        logger.error(f"Error sending winner message: {e}")


async def daily_task_scheduler():
    """Run winner picker every 24 hours."""
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), datetime.min.time()) + timedelta(days=1)
        wait_time = (target - now).total_seconds()
        logger.info(f"Next draw in {wait_time / 3600:.1f} hours...")
        await asyncio.sleep(wait_time)
        await pick_daily_winner()


# =====================================================
# RUN
# =====================================================
async def main():
    logger.info("🎯 Starting MegaWin Raffle Bot...")
    await init_db()
    asyncio.create_task(daily_task_scheduler())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
