"""Database setup (SQLAlchemy)."""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings


def _normalize_database_url(url: str) -> str:
    """
    Normalize common PostgreSQL URLs for SQLAlchemy 2.x.

    - Accepts `postgresql://...` and upgrades it to the psycopg (v3) driver:
      `postgresql+psycopg://...`
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


settings = get_settings()
if not settings.database_url:
    raise RuntimeError("DATABASE_URL is not set. Add it to backend/.env (example: postgresql://user:pass@localhost:5432/db)")

DATABASE_URL = _normalize_database_url(settings.database_url)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

