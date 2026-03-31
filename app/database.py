"""Setup SQLAlchemy engine e session per SQLite."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # Necessario per SQLite
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Classe base per tutti i modelli ORM."""

    pass


def get_db() -> Generator[Session, None, None]:
    """Dependency injection per ottenere una sessione database."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
