import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://customs:customs@localhost:5432/customs",
)


class Base(DeclarativeBase):
    pass


# engine and SessionLocal are created lazily so that tests can override
# DATABASE_URL via the environment *before* this module is imported, or
# replace the dependency entirely via FastAPI's dependency_overrides.
_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        url = os.getenv("DATABASE_URL", DATABASE_URL)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, pool_pre_ping=not url.startswith("sqlite"), connect_args=connect_args)
    return _engine


def _get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())
    return _SessionLocal


# Convenience aliases used by the rest of the application
@property
def engine():
    return _get_engine()


SessionLocal = None  # kept for backward compat; use _get_session_local() internally


def get_db():
    """FastAPI dependency — yields a DB session and closes it when done."""
    Session = _get_session_local()
    db = Session()
    try:
        yield db
    finally:
        db.close()
