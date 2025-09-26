import os
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command

from app.database import (
    SessionLocal,
    get_or_create_user,
    add_ticket,
    get_user_tickets,
    get_all_participants,
)

# Load environment variables
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing in .env")

# Setup logging
logging.basicConfig(level=logging.INFO)

# Bot and Dispatcher
bot = Bot(token=TOKEN, parse_mode="Markdown")
dp = Dispatcher()


# -------------------------
# User Commands
# -------------------------

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Welcome message + registration in DB"""
    db = SessionLocal()
    get_or_create_user(db, message.from_user)

    text = (
        f"🎉 *Welcome to MegaWin Raffle!* 🎉\n\n"
        f"Hi *{message.from_user.full_name}* 👋\n\n"
        f"Here you can:\n"
        f"🎟 Buy raffle tickets\n"
        f"📊 Check your tickets\n"
        f"🏆 Wait for the admin to pick lucky winners!\n\n"
        f"👉 To buy a ticket, type /buy\n"
        f"👉 To see your tickets, type /tickets\n"
        f"👉 For commands, type /help\n"
    )
    await message.answer(text)


@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    """Simulate buying a ticket (adds to DB)"""
    db = SessionLocal()
    user = get_or_create_user(db, message.from_user)
    add_ticket(db, user)

    await message.answer("✅ Your raffle ticket has been added! 🎟\nGood luck 🍀")


@dp.message(Command("tickets"))
async def cmd_tickets(message: Message):
    """Show all tickets owned by the user"""
    db = SessionLocal()
    user = get_or_create_user(db, message.from_user)
    tickets = get_user_tickets(db, user)

    if tickets:
        await message.answer(
            f"🎟 You have *{len(tickets)}* tickets:\n" +
            ", ".join([str(t.id) for t in tickets])
        )
    else:
        await message.answer("😕 You don’t have any tickets yet. Type /buy to get one.")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Show available commands"""
    if message.from_user.id == ADMIN_ID:
        text = (
            "🤖 *MegaWin Raffle Bot Help*\n\n"
            "👤 *User Commands:*\n"
            "/start - Start the bot & register\n"
            "/buy - Buy a raffle ticket\n"
            "/tickets - View your tickets\n"
            "/help - Show this help message\n\n"
            "🛠️ *Admin Commands:*\n"
            "/participants - List all participants\n"
            "/select_winner - Show participants to select a winner\n"
            "/winner <id> - Announce a winner\n"
            "/broadcast <msg> - Send a message to all users\n"
        )
    else:
        text = (
            "🤖 *MegaWin Raffle Bot Help*\n\n"
            "👤 *User Commands:*\n"
            "/start - Start the bot & register\n"
            "/buy - Buy a raffle ticket\n"
            "/tickets - View your tickets\n"
            "/help - Show this help message\n"
        )

    await message.answer(text)


# -------------------------
# Admin-only commands
# -------------------------

@dp.message(Command("participants"))
async def cmd_participants(message: Message):
    """Admin: see all participants"""
    if message.from_user.id != ADMIN_ID:
        return

    db = SessionLocal()
    users = get_all_participants(db)
    if not users:
        await message.answer("No participants yet.")
        return

    text = "👥 *Participants:*\n"
    for u in users:
        text += f"- {u.full_name} (@{u.username}) — {len(u.tickets)} tickets\n"

    await message.answer(text)


@dp.message(Command("select_winner"))
async def cmd_select_winner(message: Message):
    """Admin: manually select a winner"""
    if message.from_user.id != ADMIN_ID:
        return

    db = SessionLocal()
    users = get_all_participants(db)
    if not users:
        await message.answer("No participants to select from.")
        return

    text = "🏆 *Select a Winner by ID:*\n"
    for u in users:
        text += f"- `{u.id}` {u.full_name} (@{u.username}) — {len(u.tickets)} tickets\n"

    text += "\n👉 Reply with `/winner <id>` to select the winner."
    await message.answer(text)


@dp.message(Command("winner"))
async def cmd_winner(message: Message):
    """Admin: confirm a winner by user ID"""
    if message.from_user.id != ADMIN_ID:
        return

    try:
        user_id = int(message.text.split(" ")[1])
    except (IndexError, ValueError):
        await message.answer("⚠️ Usage: `/winner <id>`")
        return

    db = SessionLocal()
    users = get_all_participants(db)
    winner = next((u for u in users if u.id == user_id), None)

    if not winner:
        await message.answer("❌ No user found with that ID.")
        return

    # Announce in channel
    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"🥳 Congratulations *{winner.full_name}* (@{winner.username})!\n"
             f"You are the WINNER of this raffle! 🎉🎟"
    )
    await message.answer("✅ Winner has been announced.")


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    """Admin: broadcast a message to all participants"""
    if message.from_user.id != ADMIN_ID:
        return

    db = SessionLocal()
    users = get_all_participants(db)

    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("⚠️ Usage: `/broadcast <message>`")
        return

    for u in users:
        try:
            await bot.send_message(chat_id=u.telegram_id, text=f"📢 {text}")
        except Exception as e:
            logging.warning(f"Could not send message to {u.telegram_id}: {e}")

    await message.answer("✅ Broadcast sent to all participants.")


# -------------------------
# Run Bot
# -------------------------

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
