import os
import logging
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from dotenv import load_dotenv
from app.database import SessionLocal, get_or_create_user, add_ticket, get_user_tickets, get_all_participants

# Load environment variables
load_dotenv()

# Telegram bot info
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Paystack credentials
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")

# Initialize bot
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ------------------- COMMAND HANDLERS -------------------

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db = SessionLocal()
    get_or_create_user(db, message.from_user)
    db.close()

    welcome_text = (
        f"🎉 Welcome <b>{message.from_user.full_name}</b> to <b>MegaWin Raffle!</b>\n\n"
        "Buy raffle tickets to stand a chance of winning amazing prizes every week!\n\n"
        "✨ Commands:\n"
        "• /buy - Purchase raffle tickets\n"
        "• /tickets - View your tickets\n"
        "• /verify <reference> - Confirm your payment\n"
        "• /help - See all commands again\n\n"
        "Good luck! 🍀"
    )
    await message.answer(welcome_text)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🆘 <b>Raffle Bot Help</b>\n\n"
        "Here are the commands you can use:\n"
        "• /buy - Purchase raffle tickets\n"
        "• /verify <reference> - Verify payment & get your ticket\n"
        "• /tickets - See how many tickets you have\n"
        "• /select_winner - (Admin only) Choose a winner\n"
        "• /announce - (Admin only) Announce in channel"
    )
    await message.answer(help_text)


@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    """Start a Paystack payment"""
    amount = 500 * 100  # ₦500 in kobo
    email = f"user{message.from_user.id}@example.com"  # test email

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "email": email,
        "amount": amount,
        "callback_url": "https://example.com/paystack/webhook",  # optional
        "metadata": {"telegram_id": message.from_user.id},
    }

    response = requests.post(f"{PAYSTACK_BASE_URL}/transaction/initialize", headers=headers, json=data)

    if response.status_code == 200:
        payment_data = response.json()
        pay_url = payment_data["data"]["authorization_url"]
        await message.answer(
            f"💳 Click below to complete your payment:\n\n"
            f"👉 <a href='{pay_url}'>Pay ₦500 via Paystack</a>\n\n"
            f"After payment, send the reference using:\n"
            f"<code>/verify your_reference_here</code>",
            parse_mode="HTML"
        )
    else:
        await message.answer("⚠️ Error connecting to Paystack. Please try again later.")


@dp.message(Command("verify"))
async def cmd_verify(message: types.Message):
    """Verify Paystack payment"""
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Usage: /verify <reference>")
        return

    reference = parts[1]
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}

    response = requests.get(f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}", headers=headers)
    data = response.json()

    if response.status_code == 200 and data["data"]["status"] == "success":
        db = SessionLocal()
        user = get_or_create_user(db, message.from_user)
        add_ticket(db, user)
        db.close()
        await message.answer("✅ Payment verified successfully! 1 ticket added to your account.")
    else:
        await message.answer("❌ Payment not verified. Please check your reference and try again.")


@dp.message(Command("tickets"))
async def cmd_tickets(message: types.Message):
    """Show how many tickets the user has"""
    db = SessionLocal()
    user = get_or_create_user(db, message.from_user)
    ticket_count = get_user_tickets(db, user)
    db.close()
    await message.answer(f"🎟 You currently have <b>{ticket_count}</b> raffle ticket(s).")


@dp.message(Command("select_winner"))
async def cmd_select_winner(message: types.Message):
    """Admin manually selects a winner"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⚠️ You don’t have permission to do that.")
        return

    db = SessionLocal()
    participants = get_all_participants(db)
    db.close()

    if not participants:
        await message.answer("No participants yet.")
        return

    participant_list = "\n".join([f"{p.full_name} (@{p.username or 'NoUsername'})" for p in participants])
    await message.answer(f"🎯 <b>All Participants:</b>\n{participant_list}\n\nReply with the name of the winner you choose.")
    # You can add logic to manually record admin’s winner choice later.


@dp.message(Command("announce"))
async def cmd_announce(message: types.Message):
    """Admin sends a message to the raffle channel"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⚠️ Only the admin can use this command.")
        return

    text = message.text.replace("/announce", "").strip()
    if not text:
        await message.answer("Usage: /announce <message>")
        return

    await bot.send_message(CHANNEL_ID, f"📢 Announcement:\n\n{text}")
    await message.answer("✅ Message sent to the raffle channel.")


# ------------------- RUN BOT -------------------

if __name__ == "__main__":
    logging.info("Starting MegaWin Raffle Bot...")
    import asyncio
    from aiogram import executor

    async def main():
        await dp.start_polling(bot)

    asyncio.run(main())
