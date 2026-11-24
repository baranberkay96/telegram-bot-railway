"""Bot commands. Add your own handlers in register() at the bottom.

The asyncpg pool is in context.bot_data["pool"] (None without a database).
"""
from __future__ import annotations

import datetime as dt
import html
import logging
import re
import time

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

log = logging.getLogger("bot.handlers")

MAX_NOTES_PER_CHAT = 200
MAX_REMINDERS_PER_USER = 25
MAX_DELAY = dt.timedelta(days=365)
UNITS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
PART = re.compile(r"(\d+)([wdhms])")

COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "What this bot can do"),
    BotCommand("note", "Save a note: /note text"),
    BotCommand("notes", "List the notes of this chat"),
    BotCommand("delnote", "Delete a note: /delnote id"),
    BotCommand("remind", "Reminder: /remind 10m text"),
    BotCommand("reminders", "Your pending reminders"),
    BotCommand("cancel", "Cancel a reminder: /cancel id"),
    BotCommand("id", "Show the chat id and your user id"),
    BotCommand("ping", "Check the bot and its database"),
]

HELP = (
    "<b>Commands</b>\n"
    "/note <i>text</i> - save a note in this chat\n"
    "/notes - list this chat's notes\n"
    "/delnote <i>id</i> - delete a note\n"
    "/remind <i>10m|1h30m|2d</i> <i>text</i> - remind you here later\n"
    "/reminders - your pending reminders\n"
    "/cancel <i>id</i> - cancel a reminder\n"
    "/id - chat id and your user id\n"
    "/ping - bot and database status"
)


def parse_delay(text: str) -> dt.timedelta | None:
    """'90' (minutes), '10m', '1h30m', '2d', '1w' -> timedelta; None if invalid."""
    text = text.strip().lower()
    if text.isdigit():
        seconds = int(text) * 60
    else:
        parts = PART.findall(text)
        if not parts or "".join(n + u for n, u in parts) != text:
            return None
        seconds = sum(int(n) * UNITS[u] for n, u in parts)
    if seconds < 1:
        return None
    delay = dt.timedelta(seconds=seconds)
    return delay if delay <= MAX_DELAY else None


def _pool(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data.get("pool")


async def _no_db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if _pool(context) is None:
        await update.effective_message.reply_text("This command needs the database (DATABASE_URL).")
        return True
    return False


async def track_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remember every chat the bot sees (used by /ping stats; runs before the other handlers)."""
    pool, chat = _pool(context), update.effective_chat
    if pool is None or chat is None:
        return
    await pool.execute(
        "INSERT INTO chats (chat_id, chat_type, title) VALUES ($1, $2, $3) "
        "ON CONFLICT (chat_id) DO UPDATE SET last_seen = now(), title = EXCLUDED.title",
        chat.id, chat.type, chat.title or chat.username,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = html.escape(update.effective_user.first_name if update.effective_user else "there")
    await update.effective_message.reply_html(f"Hi {name}! I'm running on Railway.\n\n{HELP}")


async def help_(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html(HELP)


async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.effective_message.reply_html(
        f"Chat id: <code>{update.effective_chat.id}</code>\nYour user id: <code>{user.id if user else '?'}</code>"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pool = _pool(context)
    if pool is None:
        await update.effective_message.reply_text("Pong! Database: not configured.")
        return
    start_t = time.perf_counter()
    chats = await pool.fetchval("SELECT count(*) FROM chats")
    ms = (time.perf_counter() - start_t) * 1000
    await update.effective_message.reply_text(f"Pong! Database {ms:.1f} ms, {chats} chats known.")


async def note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _no_db(update, context):
        return
    text = " ".join(context.args).strip()
    if not text:
        await update.effective_message.reply_text("Usage: /note text to remember")
        return
    pool, chat = _pool(context), update.effective_chat
    count = await pool.fetchval("SELECT count(*) FROM notes WHERE chat_id = $1", chat.id)
    if count >= MAX_NOTES_PER_CHAT:
        await update.effective_message.reply_text(f"This chat has {MAX_NOTES_PER_CHAT} notes. Delete some first.")
        return
    note_id = await pool.fetchval(
        "INSERT INTO notes (chat_id, user_id, text) VALUES ($1, $2, $3) RETURNING id",
        chat.id, update.effective_user.id, text[:3000],
    )
    await update.effective_message.reply_text(f"Saved note #{note_id}.")


async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _no_db(update, context):
        return
    rows = await _pool(context).fetch(
        "SELECT id, text FROM notes WHERE chat_id = $1 ORDER BY id DESC LIMIT 30", update.effective_chat.id
    )
    if not rows:
        await update.effective_message.reply_text("No notes yet. Save one with /note text.")
        return
    lines = [f"<b>#{r['id']}</b> {html.escape(r['text'][:200])}" for r in rows]
    await update.effective_message.reply_html("\n".join(lines)[:4000])


async def delnote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _no_db(update, context):
        return
    if len(context.args) != 1 or not context.args[0].lstrip("#").isdigit():
        await update.effective_message.reply_text("Usage: /delnote id (see /notes)")
        return
    note_id = int(context.args[0].lstrip("#"))
    deleted = await _pool(context).fetchval(
        "DELETE FROM notes WHERE id = $1 AND chat_id = $2 RETURNING id", note_id, update.effective_chat.id
    )
    await update.effective_message.reply_text(f"Deleted note #{note_id}." if deleted else f"No note #{note_id} here.")


async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _no_db(update, context):
        return
    delay = parse_delay(context.args[0]) if context.args else None
    text = " ".join(context.args[1:]).strip()
    if delay is None or not text:
        await update.effective_message.reply_text("Usage: /remind 10m text (also 1h30m, 2d, 1w; up to 365 days)")
        return
    pool, user = _pool(context), update.effective_user
    count = await pool.fetchval("SELECT count(*) FROM reminders WHERE user_id = $1", user.id)
    if count >= MAX_REMINDERS_PER_USER:
        await update.effective_message.reply_text(f"You have {MAX_REMINDERS_PER_USER} reminders. /cancel one first.")
        return
    due = dt.datetime.now(dt.timezone.utc) + delay
    reminder_id = await pool.fetchval(
        "INSERT INTO reminders (chat_id, user_id, text, due_at) VALUES ($1, $2, $3, $4) RETURNING id",
        update.effective_chat.id, user.id, text[:3000], due,
    )
    await update.effective_message.reply_text(
        f"Reminder #{reminder_id} set for {due:%Y-%m-%d %H:%M} UTC."
    )


async def reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _no_db(update, context):
        return
    rows = await _pool(context).fetch(
        "SELECT id, text, due_at FROM reminders WHERE user_id = $1 ORDER BY due_at LIMIT $2",
        update.effective_user.id, MAX_REMINDERS_PER_USER,
    )
    if not rows:
        await update.effective_message.reply_text("You have no pending reminders.")
        return
    lines = [f"<b>#{r['id']}</b> {r['due_at']:%Y-%m-%d %H:%M} UTC: {html.escape(r['text'][:100])}" for r in rows]
    await update.effective_message.reply_html("\n".join(lines))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _no_db(update, context):
        return
    if len(context.args) != 1 or not context.args[0].lstrip("#").isdigit():
        await update.effective_message.reply_text("Usage: /cancel id (see /reminders)")
        return
    reminder_id = int(context.args[0].lstrip("#"))
    deleted = await _pool(context).fetchval(
        "DELETE FROM reminders WHERE id = $1 AND user_id = $2 RETURNING id", reminder_id, update.effective_user.id
    )
    text = f"Reminder #{reminder_id} cancelled." if deleted else f"You have no reminder #{reminder_id}."
    await update.effective_message.reply_text(text)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Only for ADMIN_USER_IDS."""
    if update.effective_user.id not in context.bot_data.get("admin_ids", frozenset()):
        return
    if await _no_db(update, context):
        return
    row = await _pool(context).fetchrow(
        "SELECT (SELECT count(*) FROM chats) AS chats, "
        "(SELECT count(*) FROM chats WHERE chat_type = 'private') AS users, "
        "(SELECT count(*) FROM notes) AS notes, (SELECT count(*) FROM reminders) AS reminders"
    )
    await update.effective_message.reply_text(
        f"Chats: {row['chats']} ({row['users']} private)\nNotes: {row['notes']}\nPending reminders: {row['reminders']}"
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Plain text in a private chat. Replace this with your own logic."""
    await update.effective_message.reply_text(
        f"You said: {update.effective_message.text[:3500]}\n\nSend /help for commands."
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Update failed: %s: %s", type(context.error).__name__, context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("Something went wrong. The error is in the bot's log.")
        except Exception:  # noqa: BLE001 - the error report itself must not raise
            pass


async def deliver_due_reminders(application: Application) -> None:
    """Send reminders whose time has come (called every few seconds by __main__)."""
    pool = application.bot_data.get("pool")
    if pool is None:
        return
    rows = await pool.fetch(
        "DELETE FROM reminders WHERE id IN ("
        " SELECT id FROM reminders WHERE due_at <= now() ORDER BY due_at LIMIT 20 FOR UPDATE SKIP LOCKED"
        ") RETURNING id, chat_id, user_id, text"
    )
    for row in rows:
        try:
            await application.bot.send_message(row["chat_id"], f"⏰ Reminder: {row['text']}")
        except Exception as err:  # noqa: BLE001 - one bad chat must not stop the others
            log.warning("Reminder #%s not delivered: %s", row["id"], type(err).__name__)


def register(application: Application) -> None:
    application.add_handler(MessageHandler(filters.ALL, track_chat), group=-1)
    for name, callback in (
        ("start", start), ("help", help_), ("id", chat_id), ("ping", ping), ("note", note),
        ("notes", notes), ("delnote", delnote), ("remind", remind), ("reminders", reminders),
        ("cancel", cancel), ("stats", stats),
    ):
        application.add_handler(CommandHandler(name, callback))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, echo)
    )
    application.add_error_handler(on_error)

