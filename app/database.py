import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models import Base  # Import Base from models.py

# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Database Configuration
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///raffle.db")

# Async SQLAlchemy Engine
engine = create_async_engine(DATABASE_URL, echo=False)

# Session factory for async interactions
async_session = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

# -----------------------------
# Initialize Database
# -----------------------------
async def init_db():
    """Create all database tables asynchronously."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables created successfully.")
