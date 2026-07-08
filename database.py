from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

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


def verify_tables() -> None:
    """Raise RuntimeError if any SQLAlchemy model table is missing."""
    expected = set(Base.metadata.tables.keys())
    present = set(inspect(engine).get_table_names())
    missing = sorted(expected - present)
    if missing:
        raise RuntimeError(f"Database initialization incomplete; missing tables: {', '.join(missing)}")


def create_sqlite_triggers() -> None:
    """Create SQLite triggers that are not represented in SQLAlchemy models."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS trg_products_create_inventory
                AFTER INSERT ON products
                BEGIN
                    INSERT OR IGNORE INTO inventory (product_id, quantity, updated_at)
                    VALUES (NEW.id, 0, CURRENT_TIMESTAMP);
                END
                """
            )
        )
    logger.info("SQLite triggers created or already exist.")


def ensure_inventory_rows() -> None:
    """Backfill inventory rows for products that predate the create-inventory trigger."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO inventory (product_id, quantity, updated_at)
                SELECT p.id, 0, CURRENT_TIMESTAMP
                FROM products p
                """
            )
        )
    logger.info("Inventory rows ensured for all products.")


def ensure_settings() -> None:
    """Reserved for default settings seeding; settings are created on first save."""
    return


def initialize_database() -> None:
    """Bootstrap a fresh or existing SQLite database in the correct order."""
    create_tables()
    verify_tables()
    create_sqlite_triggers()
    ensure_inventory_rows()

    # Seed data after schema is ready (import here to avoid circular imports at load).
    from services.auth_service import ensure_users_table

    ensure_users_table()
    ensure_settings()
    logger.info("Database initialization complete.")


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