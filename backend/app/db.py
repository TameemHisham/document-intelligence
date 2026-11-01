from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().db_url
        _engine = create_engine(
            url,
            # timeout: wait for locks instead of failing when ingest tasks write concurrently
            connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {},
            pool_pre_ping=True,
        )
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _fk_on(conn, _):
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def SessionLocal() -> Session:
    engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models
    from app.migrate import sync_schema

    sync_schema(engine(), models.PGVECTOR)


def reset_engine() -> None:
    """Used by tests after changing settings."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
