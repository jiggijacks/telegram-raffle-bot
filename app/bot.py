# app/bot.py
import os
import logging
import random
import aiohttp
import uvicorn

from fastapi import FastAPI, Request, HTTPException, Response

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand,
)

from sqlalchemy import select, func

# your own DB utilities / models
from app.database import async_session, init_db, User, RaffleEntry


# ---------------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PORT = int(os.getenv("PORT", "8080"))

# Public base URL of your deployed app, e.g. https://megawinraffle.up.railway.app
PUBLIC_URL = os.getenv("PUBLIC_URL")
TELEGRAM_WEBHOOK_PATH = "/webhook/telegram"
PAYSTACK_WEBHOOK_PATH = "/webhook/paystack"

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN not set in environment")

if not PUBLIC_URL:
    # We can still boot; just won't set Telegram webhook.
    logging.warning("⚠️ PUBLIC_URL not set. Telegram webhook will NOT be configured.")


# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)
logger.info("✅ Environment loaded")


# ---------------------------------------------------------
# BOT / DISPATCHER / FASTAPI
# ---------------------------------------------------------
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
app = FastAPI()


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
async def get_or_create_user(telegram_id: int, username: str | None = None) -> User:
    """Fetch user by telegram_id or create if missing."""
    async with async_session() as session:
        q = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = q.scalar_one_or_none()
        if user:
            # keep username up to date
            if username and user.username != username:
                user.username = username
                await session.commit()
            return user

        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def set_bot_commands():
    cmds = [
        BotCommand(command="start", description="Start / Referral link"),
        BotCommand(command="help", description="How to use the bot"),
        BotCommand(command="buy", description="Buy a raffle ticket (₦500)"),
        BotCommand(command="ticket", description="View your tickets"),
        BotCommand(command="referrals", description="Your referral count"),
    ]
    await bot.set_my_commands(cmds)


# ---------------------------------------------------------
# COMMAND HANDLERS
# ---------------------------------------------------------
@dp.message(Command("start"))
async def cmd_start(message: Message, command: Command):
    """ /start [referrer_tg_id]  — includes referral logic """
    tg_id = message.from_user.id
    username = message.from_user.username
    user = await get_or_create_user(tg_id, username)

    # referral handling
    args = (command.args or "").strip()
    if args:
        try:
            ref_tg_id = int(args)
            if ref_tg_id != tg_id:
                async with async_session() as s:
                    q = await s.execute(select(User).where(User.telegram_id == ref_tg_id))
                    ref_user = q.scalar_one_or_none()
                    if ref_user:
                        # ensure the field exists (some DBs might be older)
                        current = getattr(ref_user, "referral_count", 0) or 0
                        ref_user.referral_count = current + 1
                        s.add(ref_user)

                        # 5 referrals => 1 free ticket
                        if ref_user.referral_count >= 5:
                            entry = RaffleEntry(user_id=ref_user.id, free_ticket=True)
                            s.add(entry)
                            ref_user.referral_count -= 5
                            await s.commit()
                            try:
                                await bot.send_message(
                                    ref_user.telegram_id,
                                    "🎉 <b>You referred 5 users and earned a FREE ticket!</b>",
                                )
                            except Exception as e:
                                logger.warning(f"Failed to notify referrer: {e}")
                        else:
                            await s.commit()
        except ValueError:
            pass

    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start={tg_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Buy Ticket", callback_data="buy_ticket")],
        [InlineKeyboardButton(text="🎫 My Tickets", callback_data="view_tickets")],
        [InlineKeyboardButton(text="👥 Referrals", callback_data="my_referrals")],
        [InlineKeyboardButton(text="❓ Help", callback_data="help_cmd")],
    ])

    await message.answer(
        "🎉 <b>Welcome to MegaWin Raffle!</b>\n\n"
        "Invite friends with your link (5 referrals = 1 FREE ticket):\n"
        f"<code>{ref_link}</code>\n\n"
        "Use the buttons below to get started 👇",
        reply_markup=kb,
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "💡 <b>How to play</b>\n"
        "• /buy — Buy a raffle ticket (₦500)\n"
        "• /ticket — View your tickets\n"
        "• /referrals — See your referral count\n\n"
        "<b>Admin only</b>:\n"
        "• /winners — pick a random winner\n"
        "• /stats — view platform stats"
    )


@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    """Initialize Paystack transaction and reply with payment link."""
    if not PAYSTACK_SECRET_KEY:
        await message.answer("❌ Paystack key not set.")
        return

    tg_id = message.from_user.id
    username = message.from_user.username
    user = await get_or_create_user(tg_id, username)

    callback_url = f"{PUBLIC_URL}{PAYSTACK_WEBHOOK_PATH}" if PUBLIC_URL else None

    async with aiohttp.ClientSession() as s:
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
                   "Content-Type": "application/json"}
        payload = {
            "email": f"user_{tg_id}@megawinraffle.com",
            "amount": 500 * 100,  # kobo
            "metadata": {"telegram_id": tg_id},
            "callback_url": callback_url,  # optional; webhook does server-to-server
        }
        async with s.post("https://api.paystack.co/transaction/initialize",
                          headers=headers, json=payload) as resp:
            res = await resp.json()

    if res.get("status"):
        ref = res["data"]["reference"]
        pay_url = res["data"]["authorization_url"]

        # store a placeholder entry with payment_ref so webhook can match it
        async with async_session() as s:
            s.add(RaffleEntry(user_id=user.id, payment_ref=ref, free_ticket=False))
            await s.commit()

        await message.answer(
            "💳 <b>Payment</b>\n\n"
            "Click below to complete your payment:\n"
            f"👉 <a href=\"{pay_url}\">Pay ₦500 via Paystack</a>\n\n"
            "Once payment is confirmed, your raffle ticket will be added automatically. ✅",
            disable_web_page_preview=True,
        )
    else:
        await message.answer("❌ Could not start Paystack payment. Please try again.")


@dp.message(Command("ticket"))
async def cmd_ticket(message: Message):
    tg_id = message.from_user.id
    async with async_session() as s:
        q = await s.execute(select(User).where(User.telegram_id == tg_id))
        user = q.scalar_one_or_none()
        if not user:
            await message.answer("🚫 You don't have any tickets yet.")
            return

        q2 = await s.execute(select(RaffleEntry).where(RaffleEntry.user_id == user.id))
        tickets = q2.scalars().all()
        if not tickets:
            await message.answer("🚫 You have no tickets yet. Use /buy.")
            return

        parts = []
        for t in tickets:
            kind = "Free" if getattr(t, "free_ticket", False) else "Paid"
            when = getattr(t, "created_at", None)
            when_txt = when.strftime("%Y-%m-%d %H:%M") if when else "-"
            parts.append(f"🎫 #{t.id} | {kind} | {when_txt}")

        await message.answer("\n".join(parts))


@dp.message(Command("referrals"))
async def cmd_referrals(message: Message):
    tg_id = message.from_user.id
    async with async_session() as s:
        q = await s.execute(select(User).where(User.telegram_id == tg_id))
        user = q.scalar_one_or_none()
        count = getattr(user, "referral_count", 0) if user else 0
        await message.answer(f"👥 You have referred <b>{count}</b> user(s).")


@dp.message(Command("winners"))
async def cmd_winners(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Only admin can run this command.")
        return

    async with async_session() as s:
        q = await s.execute(select(RaffleEntry))
        entries = q.scalars().all()
        if not entries:
            await message.answer("📭 No tickets yet.")
            return

        winner = random.choice(entries)
        q2 = await s.execute(select(User).where(User.id == winner.user_id))
        user = q2.scalar_one_or_none()
        who = f"@{user.username}" if user and user.username else str(getattr(user, "telegram_id", "unknown"))
        await message.answer(f"🏆 <b>Winner:</b> {who}\n🎫 Ticket #{winner.id}")


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Only admin can view stats.")
        return

    async with async_session() as s:
        total_users = await s.scalar(select(func.count(User.id)))
        total_tickets = await s.scalar(select(func.count(RaffleEntry.id)))
        total_free = await s.scalar(select(func.count(RaffleEntry.id)).where(RaffleEntry.free_ticket == True))

    await message.answer(
        "📊 <b>Stats</b>\n"
        f"👥 Users: {total_users or 0}\n"
        f"🎟 Tickets: {total_tickets or 0}\n"
        f"🆓 Free: {total_free or 0}"
    )


# ---------------------------------------------------------
# CALLBACKS
# ---------------------------------------------------------
@dp.callback_query(F.data == "buy_ticket")
async def cb_buy(callback: CallbackQuery):
    await cmd_buy(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "view_tickets")
async def cb_tickets(callback: CallbackQuery):
    await cmd_ticket(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "my_referrals")
async def cb_ref(callback: CallbackQuery):
    await cmd_referrals(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "help_cmd")
async def cb_help(callback: CallbackQuery):
    await cmd_help(callback.message)
    await callback.answer()


# ---------------------------------------------------------
# WEBHOOK ROUTES
# ---------------------------------------------------------
@app.post(PAYSTACK_WEBHOOK_PATH)
async def paystack_webhook(request: Request):
    """Handle Paystack -> server webhook and add/confirm tickets."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    event = payload.get("event")
    data = payload.get("data", {})
    logger.info(f"📩 Paystack event: {event}")

    if event != "charge.success" or data.get("status") != "success":
        return {"status": "ignored"}

    tg_id = data.get("metadata", {}).get("telegram_id")
    reference = data.get("reference")
    if not tg_id or not reference:
        raise HTTPException(status_code=400, detail="missing telegram_id or reference")

    # verify reference with Paystack
    async with aiohttp.ClientSession() as s:
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        async with s.get(url, headers=headers) as resp:
            v = await resp.json()

    if not (v.get("status") and v["data"]["status"] == "success"):
        raise HTTPException(status_code=400, detail="verification failed")

    # mark/ensure entry
    async with async_session() as db:
        # ensure user exists
        uq = await db.execute(select(User).where(User.telegram_id == tg_id))
        user = uq.scalar_one_or_none()
        if not user:
            user = User(telegram_id=tg_id)
            db.add(user)
            await db.flush()

        # if we created a placeholder earlier by reference, fine; else insert now
        q = await db.execute(select(RaffleEntry).where(RaffleEntry.payment_ref == reference))
        entry = q.scalar_one_or_none()
        if not entry:
            entry = RaffleEntry(user_id=user.id, payment_ref=reference, free_ticket=False)
            db.add(entry)

        await db.commit()

    # notify user
    try:
        await bot.send_message(
            chat_id=int(tg_id),
            text="✅ <b>Payment confirmed!</b>\nYour raffle ticket has been added.\nUse /ticket to view your tickets.",
        )
    except Exception as e:
        logger.warning(f"Failed to notify user {tg_id}: {e}")

    return {"status": "ok"}


@app.post(TELEGRAM_WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """Handle Telegram -> server webhook."""
    body = await request.json()
    try:
        update = types.Update.model_validate(body)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid telegram update")
    await dp.feed_update(bot, update)
    return Response(status_code=200)


# ---------------------------------------------------------
# FASTAPI LIFECYCLE
# ---------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    await init_db()
    await set_bot_commands()
    if PUBLIC_URL:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await bot.set_webhook(f"{PUBLIC_URL}{TELEGRAM_WEBHOOK_PATH}",
                                  allowed_updates=["message", "callback_query"])
            logger.info("✅ Telegram webhook set")
        except Exception as e:
            logger.error(f"❌ Failed to set Telegram webhook: {e}")
    else:
        logger.warning("PUBLIC_URL not set: Telegram webhook NOT configured.")

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass


# ---------------------------------------------------------
# ENTRY POINT (NO asyncio.run INSIDE)
# ---------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
