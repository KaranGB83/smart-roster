from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

_engine = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        # prepare_threshold=None: required for Supabase's transaction pooler (pgbouncer, port 6543)
        _engine = create_engine(
            get_settings().sqlalchemy_url,
            pool_pre_ping=True,
            connect_args={"prepare_threshold": None},
        )
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_db() -> Iterator[Session]:
    get_engine()
    assert _SessionLocal is not None
    with _SessionLocal() as session:
        yield session
