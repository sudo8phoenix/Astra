"""Database configuration and session management."""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from pydantic_settings import BaseSettings
from typing import Generator
import os

# Declare the base class for all models
Base = declarative_base()


class DatabaseSettings(BaseSettings):
    """Database configuration from environment variables."""

    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 5432))
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "postgres")
    DB_NAME: str = os.getenv("DB_NAME", "ai_assistant")
    SQLALCHEMY_POOL_SIZE: int = 20
    SQLALCHEMY_POOL_RECYCLE: int = 3600
    SQLALCHEMY_POOL_PRE_PING: bool = True

    class Config:
        env_file = ".env"

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL."""
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


# Initialize settings
db_settings = DatabaseSettings()

# Create engine
engine = create_engine(
    db_settings.database_url,
    poolclass=QueuePool,
    pool_size=db_settings.SQLALCHEMY_POOL_SIZE,
    max_overflow=10,
    pool_recycle=db_settings.SQLALCHEMY_POOL_RECYCLE,
    pool_pre_ping=db_settings.SQLALCHEMY_POOL_PRE_PING,
    echo=False,  # Set to True for SQL debugging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables in the database."""
    Base.metadata.create_all(bind=engine)


def drop_all_tables():
    """Drop all tables (use only in development/testing)."""
    Base.metadata.drop_all(bind=engine)
