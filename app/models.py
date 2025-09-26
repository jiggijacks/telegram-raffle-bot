# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tg_user_id = Column(String, unique=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    payments = relationship("Payment", back_populates="user")
    entries = relationship("Entry", back_populates="user")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String)
    provider_ref = Column(String, unique=True, index=True)
    amount = Column(Numeric(12,2))
    currency = Column(String, default="NGN")
    status = Column(String)
    raw = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="payments")

class Raffle(Base):
    __tablename__ = "raffles"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="Manual Draw")
    prize = Column(String, default="Prize")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    entries = relationship("Entry", back_populates="raffle")
    winners = relationship("Winner", back_populates="raffle")

class Entry(Base):
    __tablename__ = "entries"
    id = Column(Integer, primary_key=True, index=True)
    raffle_id = Column(Integer, ForeignKey("raffles.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    raffle = relationship("Raffle", back_populates="entries")
    user = relationship("User", back_populates="entries")

class Winner(Base):
    __tablename__ = "winners"
    id = Column(Integer, primary_key=True, index=True)
    raffle_id = Column(Integer, ForeignKey("raffles.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    position = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    raffle = relationship("Raffle", back_populates="winners")
