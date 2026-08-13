"""
SQLAlchemy database setup — Milestone 7.

CONCEPT
  Engine + Session factory + Base metadata.
  SQLite now; switch DATABASE_URL to PostgreSQL later without rewriting domain code.

SPRING ANALOGY
  Like DataSource + EntityManagerFactory configuration.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import Settings, get_settings


class Base(DeclarativeBase):
    """ORM declarative base (≈ @MappedSuperclass / shared Entity base)."""


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    if database_url.startswith("sqlite:///./") or database_url.startswith("sqlite:///"):
        # sqlite:///./data/foo.db  or  sqlite:///C:/...
        raw = database_url.removeprefix("sqlite:///")
        if raw.startswith("./"):
            path = Path(raw)
            path.parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(settings: Settings | None = None):
    settings = settings or get_settings()
    _ensure_sqlite_parent_dir(settings.database_url)

    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        # Needed for FastAPI multi-thread request handling with SQLite
        connect_args["check_same_thread"] = False

    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        future=True,
    )

    if settings.database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_db_engine()
        _SessionLocal = sessionmaker(
            bind=_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _engine


def get_session_factory():
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def reset_db_engine_for_tests() -> None:
    """Clear cached engine/session (used by pytest with temp DB URLs)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db(settings: Settings | None = None) -> None:
    """Create tables if they do not exist (learning-friendly; migrations later)."""
    # Import models so metadata is populated
    from app.infrastructure.persistence import models  # noqa: F401

    settings = settings or get_settings()
    reset_db_engine_for_tests()
    # Force engine with current settings
    global _engine, _SessionLocal
    _engine = create_db_engine(settings)
    _SessionLocal = sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(bind=_engine)


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency ≈ @Transactional EntityManager per request."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
