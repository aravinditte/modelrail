"""Engine/session management. PostgreSQL in production; SQLite for local
tests and demos through the same DATABASE_URL mechanism."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..config import get_settings
from .models import Base

_engine = None
_Session = None


def get_engine():
    global _engine, _Session
    if _engine is None:
        url = get_settings().database_url
        connect_args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True, future=True)
        if url.startswith("sqlite"):
            # Local/demo store tuning: WAL lets readers proceed while a write
            # is in flight; NORMAL sync keeps commits cheap. PostgreSQL (the
            # production store) is unaffected.
            from sqlalchemy import event

            @event.listens_for(_engine, "connect")
            def _sqlite_pragmas(dbapi_connection, _record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()

        _Session = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)
    return _engine


def get_session_factory():
    get_engine()
    return _Session


def init_db() -> None:
    get_engine()
    Base.metadata.create_all(bind=_engine)


def reset_engine() -> None:
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None


def db_session():
    """FastAPI dependency."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()
