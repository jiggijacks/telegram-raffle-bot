from sqlalchemy import Column, Integer, String, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Database setup
DATABASE_URL = "sqlite:///raffle.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# -------------------------
# Models
# -------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)

    tickets = relationship("Ticket", back_populates="owner")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="tickets")


# -------------------------
# Database Helpers
# -------------------------

def init_db():
    """Create tables if they don’t exist"""
    Base.metadata.create_all(bind=engine)


def get_or_create_user(db, telegram_user):
    """Find or create a User entry"""
    user = db.query(User).filter(User.telegram_id == telegram_user.id).first()
    if not user:
        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            full_name=telegram_user.full_name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def add_ticket(db, user: User):
    """Assign a new raffle ticket to a user"""
    ticket = Ticket(owner=user)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def get_user_tickets(db, user: User):
    """Return all tickets belonging to a user"""
    return db.query(Ticket).filter(Ticket.user_id == user.id).all()


def get_all_participants(db):
    """Return all users who have tickets"""
    return db.query(User).filter(User.tickets.any()).all()


# -------------------------
# Run directly for setup
# -------------------------

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized (raffle.db created/updated).")
