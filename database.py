from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from models import Base


logger = logging.getLogger(__name__)

# Keep database file inside the project at database/warehouse.db
DB_PATH = Path(__file__).resolve().parent / "database" / "warehouse.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    class_=Session,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
    del connection_record
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_tables() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Initializing database at %s", DB_PATH)
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created or already exist.")


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Session transaction failed and was rolled back.")
        raise
    finally:
        session.close()