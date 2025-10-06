import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
import os

# Get database URL (defaults to local SQLite)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///raffle.db")

# Create Base model class
Base = declarative_base()

# Define RaffleEntry model
class RaffleEntry(Base):
    __tablename__ = "raffle_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Create async database engine
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Utility function to initialize DB
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
