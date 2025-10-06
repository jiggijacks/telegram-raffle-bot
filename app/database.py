import os
from sqlalchemy import Column, Integer, String, ForeignKey, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ==================================================
# Database setup
# ==================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./raffle.db")

# Create async engine and session
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# ==================================================
# Models
# ==================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    tickets = relationship("Ticket", back_populates="user")

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="tickets")

# ==================================================
# Initialize database
# ==================================================
async def init_db():
    """Create all tables when bot starts."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ==================================================
# Utility functions
# ==================================================
async def get_or_create_user(db: AsyncSession, telegram_user):
    result = await db.execute(select(User).filter(User.telegram_id == telegram_user.id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            full_name=telegram_user.full_name
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user

async def add_ticket(db: AsyncSession, telegram_id: int):
    result = await db.execute(select(User).filter(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user:
        ticket = Ticket(user_id=user.id)
        db.add(ticket)
        await db.commit()
        await db.refresh(ticket)
        return ticket
    return None

async def get_user_tickets(db: AsyncSession, telegram_id: int):
    result = await db.execute(select(User).filter(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        return []

    result = await db.execute(select(Ticket).filter(Ticket.user_id == user.id))
    tickets = result.scalars().all()
    return tickets

async def get_all_participants(db: AsyncSession):
    result = await db.execute(select(User))
    return result.scalars().all()
