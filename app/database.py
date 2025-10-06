import os
import asyncio
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# =====================================================
# Database configuration
# =====================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./raffle.db")

Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


# =====================================================
# MODELS
# =====================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    full_name = Column(String)
    tickets = relationship("Ticket", back_populates="owner")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="tickets")


# =====================================================
# INITIALIZATION
# =====================================================
async def init_db():
    """Initialize database (create tables if not exist)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# =====================================================
# HELPERS
# =====================================================
async def get_or_create_user(telegram_id: int, full_name: str):
    async with async_session() as session:
        result = await session.execute(
            User.__table__.select().where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(telegram_id=telegram_id, full_name=full_name)
            session.add(user)
            await session.commit()
            await session.refresh(user)

        return user


async def add_ticket(user_id: int):
    async with async_session() as session:
        ticket = Ticket(user_id=user_id)
        session.add(ticket)
        await session.commit()
        return ticket


async def get_user_tickets(user_id: int):
    async with async_session() as session:
        result = await session.execute(
            Ticket.__table__.select().where(Ticket.user_id == user_id)
        )
        tickets = result.fetchall()
        return tickets


async def get_all_participants():
    async with async_session() as session:
        result = await session.execute(User.__table__.select())
        users = result.fetchall()
        return users


# =====================================================
# TEST (optional)
# =====================================================
if __name__ == "__main__":
    asyncio.run(init_db())
    print("✅ Database initialized successfully.")
