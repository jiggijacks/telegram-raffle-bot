# app/utils.py
import os, secrets

TICKET_PRICE = int(float(os.getenv("TICKET_PRICE", "500")))

def kobo(amount_ngn: int) -> int:
    """Convert NGN to kobo (integer) for Paystack."""
    return int(amount_ngn) * 100

def generate_reference(prefix="RAFF"):
    return f"{prefix}_{secrets.token_hex(8)}"
