"""Explicit SQLite engine creation with foreign keys and read-snapshot transactions."""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite:"):
        raise ValueError("This prototype supports SQLite only")
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def configure_connection(connection, _):
        # Disable sqlite3's legacy implicit transaction control (including SELECT).
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN")

    return engine
