from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings

Base = declarative_base()


@lru_cache(maxsize=None)
def get_engine(database_url: str | None = None):
    return create_engine(database_url or get_settings().database_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=None)
def get_session_factory(database_url: str | None = None):
    return sessionmaker(bind=get_engine(database_url), autoflush=False, expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    session = get_session_factory(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(database_url: str | None = None) -> None:
    from app.infrastructure import models  # noqa: F401

    Base.metadata.create_all(get_engine(database_url))
