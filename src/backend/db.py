"""Read-only access to the stock database through a small connection pool."""

from typing import Any, Sequence

import mysql.connector
from mysql.connector import pooling

from .config import Settings

_pool: pooling.MySQLConnectionPool | None = None


def init_pool(settings: Settings, size: int = 5) -> None:
    global _pool
    _pool = pooling.MySQLConnectionPool(
        pool_name="diagram",
        pool_size=size,
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        autocommit=True,
    )


def rows(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[dict[str, Any]]:
    """Run a SELECT and return its rows as dicts."""
    if _pool is None:
        raise RuntimeError("database pool is not initialised")
    connection = _pool.get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql, params)
        result = cursor.fetchall()
        cursor.close()
        return result
    finally:
        connection.close()


def one(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> dict[str, Any] | None:
    found = rows(sql, params)
    return found[0] if found else None


def scalar(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> Any:
    found = one(sql, params)
    return next(iter(found.values())) if found else None


def check_connection() -> None:
    """Raise mysql.connector.Error if the database cannot be reached."""
    scalar("SELECT 1")


Error = mysql.connector.Error
