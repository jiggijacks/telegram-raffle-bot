import os
import logging
import requests
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import (
    async_session,
    init_db,
    get_or_create_user,
    add_ticket,
    get_user_tickets,
    get_all_participants,
)

# ==================================================
# Logging setup
# ==================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================================================
# Environment variables
# ==================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")

# ==================================================
# Bot and Dispatcher
# ==================================================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
router = Router()

# ==================================================
# Helper: Create Paystack payment link
# ==================================================
def create_paystack_payment(email: str, amount_kobo: int):
    try:
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        data = {"email": email, "amount": amount_kobo}
        response = requests.post("https://api.paystack.co/transaction/initialize", json=data, headers=headers)
        res_json = response.json()
        if res_json.get("status"):
            return res_json["data"]["authorization_url"]
        else:
            return None
    except Exception as e:
        logger.error(f"Paystack error: {e}")
        return None

# ==================================================
# Command Handlers
# ==================================================
@router.message(CommandStart())
async def cmd_start(message: Message):
    """Welcome message"""
    text = (
        f"🎉 Welcome to <b>MegaWin Raffle!</b>\n\n"
        f"Join the excitement — buy raffle tickets for a chance to win amazing prizes!\n\n"
        f"Commands:\n"
        f"🎟️ /buy — Purchase raffle tickets\n"
        f"🎫 /tickets — View your tickets\n"
        f"ℹ️ /help — Learn how it works\n\n"
        f"Good luck, {message.from_user.first_name}! 🍀"
    )

    async with async_session() as db:
        await get_or_create_user(db, message.from_user)

    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Help command"""
    help_text = (
        "📘 <b>How it works</b>\n"
        "1️⃣ Use /buy to get a ticket (₦500 each).\n"
        "2️⃣ Each ticket increases your chances to win.\n"
        "3️⃣ Winners are randomly selected weekly.\n"
        "4️⃣ View your tickets anytime with /tickets.\n\n"
        "🧾 Payments are processed securely via Paystack."
    )
    await message.answer(help_text)


@router.message(Command("buy"))
async def cmd_buy(message: Message):
    """Buy raffle ticket"""
    email = f"user_{message.from_user.id}@example.com"
    amount_kobo = 500 * 100  # ₦500 in Kobo

    link = create_paystack_payment(email, amount_kobo)
    if not link:
        await message.answer("⚠️ Could not generate Paystack link. Please try again later.")
        return

    await message.answer(
        f"💳 Click below to complete your payment:\n\n<a href='{link}'>Pay ₦500 via Paystack</a>",
        disable_web_page_preview=True,
    )


@router.message(Command("tickets"))
async def cmd_tickets(message: Message):
    """View your raffle tickets"""
    async with async_session() as db:
        tickets = await get_user_tickets(db, message.from_user.id)

    count = len(tickets)
    if count == 0:
        await message.answer("🎟️ You have no tickets yet. Use /buy to get one!")
    else:
        await message.answer(f"🎉 You have <b>{count}</b> raffle ticket(s)! Good luck!")


@router.message(Command("participants"))
async def cmd_participants(message: Message):
    """Admin-only command to view all participants"""
    if str(message.from_user.id) != str(ADMIN_ID):
        await message.answer("⛔ You are not authorized to use this command.")
        return

    async with async_session() as db:
        users = await get_all_participants(db)

    if not users:
        await message.answer("No participants yet.")
    else:
        user_list = "\n".join([f"• {u.full_name or u.username or 'User'}" for u in users])
        await message.answer(f"👥 <b>Participants</b>:\n{user_list}")

# ==================================================
# Startup and Polling
# ==================================================
async def main():
    await init_db()
    dp.include_router(router)
    logger.info("🎯 Starting MegaWin Raffle Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
