# app/webhooks.py
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from .db import get_db
from .models import User, Payment, Entry, Raffle
import os, json, hmac, hashlib

router = APIRouter()

@router.post("/paystack/webhook")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    secret = os.getenv("PAYSTACK_WEBHOOK_SECRET")
    if secret:
        sig = request.headers.get("x-paystack-signature")
        digest = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(sig or "", digest):
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success" and data.get("status") == "success":
        reference = data.get("reference")
        amount = (data.get("amount", 0) or 0) / 100.0
        currency = data.get("currency", "NGN")
        metadata = data.get("metadata") or {}
        tg_user_id = str(metadata.get("tg_user_id")) if metadata else None

        if not reference:
            return JSONResponse({"ok": True})

        user = None
        if tg_user_id:
            user = db.query(User).filter_by(tg_user_id=tg_user_id).one_or_none()
            if not user:
                user = User(tg_user_id=tg_user_id)
                db.add(user)
                db.commit()
                db.refresh(user)

        existing = db.query(Payment).filter_by(provider="paystack", provider_ref=reference).one_or_none()
        if existing:
            return JSONResponse({"ok": True})

        payment = Payment(
            provider="paystack",
            provider_ref=reference,
            amount=amount,
            currency=currency,
            status="success",
            raw=json.dumps(payload),
            user_id=user.id if user else None
        )
        db.add(payment)

        ticket_price = int(float(os.getenv("TICKET_PRICE", "500")))
        num_tickets = int(amount // ticket_price) if ticket_price > 0 else 0

        raffle = db.query(Raffle).filter_by(is_active=True).order_by(Raffle.id.desc()).first()
        if not raffle:
            raffle = Raffle(title="Manual Draw", is_active=True)
            db.add(raffle)
            db.commit()
            db.refresh(raffle)

        for _ in range(num_tickets):
            db.add(Entry(raffle_id=raffle.id, user_id=user.id if user else None))

        db.commit()
        return JSONResponse({"received": True, "tickets": num_tickets})

    return JSONResponse({"ok": True})

@router.post("/flutterwave/webhook")
async def flutterwave_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    data = payload.get("data") or payload
    status = data.get("status")
    if status in ("successful", "success"):
        tx_ref = data.get("tx_ref") or data.get("txRef") or data.get("reference")
        amount = float(data.get("amount", 0) or 0)
        currency = data.get("currency", "NGN")
        meta = data.get("meta") or {}
        tg_user_id = str(meta.get("tg_user_id")) if meta else None

        if not tx_ref:
            return JSONResponse({"ok": True})

        user = None
        if tg_user_id:
            user = db.query(User).filter_by(tg_user_id=tg_user_id).one_or_none()
            if not user:
                user = User(tg_user_id=tg_user_id)
                db.add(user)
                db.commit()
                db.refresh(user)

        exists = db.query(Payment).filter_by(provider="flutterwave", provider_ref=tx_ref).one_or_none()
        if exists:
            return JSONResponse({"ok": True})

        payment = Payment(
            provider="flutterwave",
            provider_ref=tx_ref,
            amount=amount,
            currency=currency,
            status="success",
            raw=json.dumps(payload),
            user_id=user.id if user else None
        )
        db.add(payment)

        ticket_price = int(float(os.getenv("TICKET_PRICE", "500")))
        num_tickets = int(amount // ticket_price) if ticket_price > 0 else 0

        raffle = db.query(Raffle).filter_by(is_active=True).order_by(Raffle.id.desc()).first()
        if not raffle:
            raffle = Raffle(title="Manual Draw", is_active=True)
            db.add(raffle)
            db.commit()
            db.refresh(raffle)

        for _ in range(num_tickets):
            db.add(Entry(raffle_id=raffle.id, user_id=user.id if user else None))

        db.commit()
        return JSONResponse({"received": True, "tickets": num_tickets})

    return JSONResponse({"ok": True})
