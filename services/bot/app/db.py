"""Postgres access (asyncpg pool) and the schema the starter commands use.

The schema is created with idempotent statements at every start. Add your
own tables to SCHEMA (or switch to a migration tool when it grows).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import asyncpg

log = logging.getLogger("bot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id    bigint PRIMARY KEY,
    chat_type  text        NOT NULL,
    title      text,
    first_seen timestamptz NOT NULL DEFAULT now(),
    last_seen  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS notes (
    id         bigserial PRIMARY KEY,
    chat_id    bigint      NOT NULL,
    user_id    bigint      NOT NULL,
    text       text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notes_chat_idx ON notes (chat_id, id);
CREATE TABLE IF NOT EXISTS reminders (
    id         bigserial PRIMARY KEY,
    chat_id    bigint      NOT NULL,
    user_id    bigint      NOT NULL,
    text       text        NOT NULL,
    due_at     timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reminders_due_at_idx ON reminders (due_at);
"""

RETRYABLE = (OSError, ValueError, asyncpg.PostgresError, asyncpg.InterfaceError, asyncio.TimeoutError)


async def connect(url: str, on_wait: Callable[[int, Exception], None]) -> asyncpg.Pool:
    """Open the pool, retrying until the database answers (Postgres may start later)."""
    delay, attempt = 2.0, 0
    while True:
        attempt += 1
        try:
            pool = await asyncpg.create_pool(url, min_size=1, max_size=5, command_timeout=30)
            async with pool.acquire() as conn:
                await conn.execute(SCHEMA)
            log.info("Database ready")
            return pool
        except RETRYABLE as err:
            on_wait(attempt, err)
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 30.0)
