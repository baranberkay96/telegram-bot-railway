"""Entry point: HTTP server, database, then the Telegram bot (webhook or polling).

Configuration problems (no token, wrong token, no database) never crash the
service. They are logged with what to fix, and the process stays up with a
200 health endpoint, so a deploy with a placeholder token succeeds and a
fixed variable plus redeploy is all it takes. The token is never logged.
"""
from __future__ import annotations

import asyncio
import logging
import re
import signal

import asyncpg
from telegram import Update
from telegram.error import BadRequest, InvalidToken, NetworkError, RetryAfter, TelegramError
from telegram.ext import Application

from . import config as config_module
from . import db, handlers
from .web import WEBHOOK_PATH, WebServer

log = logging.getLogger("bot")
TOKEN_HELP = (
    "Set TELEGRAM_BOT_TOKEN on the Bot service to the token @BotFather gave you "
    "(send /mybots, your bot, API Token) and redeploy."
)
WEBHOOK_ATTEMPTS = 6  # then fall back to polling so the bot still works
REMINDER_INTERVAL = 10


def redact(text: str) -> str:
    """Remove passwords from URLs and anything shaped like a bot token."""
    text = re.sub(r"(://[^:/@\s]+:)[^@\s]+@", r"\1***@", text)
    return re.sub(r"\d{6,}:[A-Za-z0-9_-]{20,}", "***", text)


async def idle(web: WebServer, state: str, detail: str) -> None:
    web.set_state(state, detail)
    await asyncio.Event().wait()  # until Railway stops or redeploys the service


async def open_database(cfg: config_module.Config, web: WebServer) -> asyncpg.Pool | None:
    if not cfg.database_url:
        log.warning("DATABASE_URL is empty: notes and reminders are disabled.")
        return None

    def on_wait(attempt: int, err: Exception) -> None:
        web.set_state("waiting-for-database", type(err).__name__)
        log.warning("Database not reachable yet (attempt %d): %s: %s",
                    attempt, type(err).__name__, redact(str(err))[:200])

    web.set_state("waiting-for-database")
    return await db.connect(cfg.database_url, on_wait)


def build_application(cfg: config_module.Config, pool: asyncpg.Pool | None) -> Application:
    builder = Application.builder().token(cfg.token)
    if cfg.api_url:  # a self-hosted Bot API server (github.com/tdlib/telegram-bot-api)
        builder = builder.base_url(f"{cfg.api_url}/bot").base_file_url(f"{cfg.api_url}/file/bot")
    application = builder.build()
    application.bot_data["pool"] = pool
    application.bot_data["admin_ids"] = cfg.admin_ids
    handlers.register(application)
    return application


async def set_webhook(application: Application, cfg: config_module.Config) -> bool:
    """Register https://<domain>/telegram with Telegram. False: use polling instead."""
    url = f"https://{cfg.public_domain}{WEBHOOK_PATH}"
    delay = 10.0
    for attempt in range(1, WEBHOOK_ATTEMPTS + 1):
        try:
            await application.bot.set_webhook(
                url, secret_token=cfg.webhook_secret, allowed_updates=Update.ALL_TYPES, max_connections=40
            )
            log.info("Webhook set to %s", url)
            return True
        except RetryAfter as err:
            await asyncio.sleep(float(getattr(err, "retry_after", 5) or 5))
        except (BadRequest, NetworkError) as err:
            # A brand-new Railway domain can take a minute to resolve for Telegram.
            log.warning("Telegram did not accept the webhook (attempt %d/%d): %s",
                        attempt, WEBHOOK_ATTEMPTS, redact(str(err))[:200])
            await asyncio.sleep(delay)
            delay = min(delay * 2, 120.0)
    log.error("Could not set the webhook to %s; falling back to polling. Check that the Bot service "
              "has a public domain and redeploy to try the webhook again.", url)
    return False


async def serve(application: Application, cfg: config_module.Config, web: WebServer) -> None:
    """Run the started application until cancelled, delivering reminders meanwhile."""
    bot = application.bot
    mode = cfg.mode
    if mode == "webhook":
        async def on_update(data: dict) -> None:
            await application.update_queue.put(Update.de_json(data, bot))

        web.set_update_handler(on_update)
        if not await set_webhook(application, cfg):
            web.set_update_handler(None)
            mode = "polling"
    if mode == "polling":
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)  # also removes a webhook
        log.info("Polling Telegram for updates")
    web.set_state("running", f"@{bot.username} ({mode})")
    log.info("Bot @%s is running in %s mode. Open https://t.me/%s and send /start", bot.username, mode, bot.username)
    while True:
        try:
            await handlers.deliver_due_reminders(application)
        except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as err:
            log.warning("Reminder delivery: database error %s; retrying", type(err).__name__)
        await asyncio.sleep(REMINDER_INTERVAL)


async def run(cfg: config_module.Config, web: WebServer) -> None:
    if not cfg.token or any(ch.isspace() for ch in cfg.token):
        log.error("TELEGRAM_BOT_TOKEN is not set. %s", TOKEN_HELP)
        await idle(web, "not-configured", "TELEGRAM_BOT_TOKEN missing")
        return

    pool = await open_database(cfg, web)
    delay = 5.0
    try:
        while True:
            web.set_state("connecting")
            application = build_application(cfg, pool)
            try:
                await application.initialize()  # getMe: checks the token
            except InvalidToken:
                # The exception text contains the token: never log it.
                log.error("Telegram rejected TELEGRAM_BOT_TOKEN (wrong or revoked). %s", TOKEN_HELP)
                await idle(web, "token-invalid", "Telegram rejected TELEGRAM_BOT_TOKEN")
                return
            except TelegramError as err:
                log.warning("Telegram not reachable: %s. Retrying in %.0f s", type(err).__name__, delay)
                web.set_state("retrying", type(err).__name__)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300.0)
                continue
            try:
                await application.bot.set_my_commands(handlers.COMMANDS)
                await application.start()
                await serve(application, cfg, web)
            except TelegramError as err:
                log.warning("Telegram error: %s: %s. Restarting the bot in %.0f s",
                            type(err).__name__, redact(str(err))[:200], delay)
                web.set_state("retrying", type(err).__name__)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300.0)
            finally:
                web.set_update_handler(None)
                if application.updater and application.updater.running:
                    await application.updater.stop()
                if application.running:
                    await application.stop()
                await application.shutdown()
    finally:
        if pool is not None:
            await pool.close()


async def main() -> None:
    logging.basicConfig(
        level=config_module.log_level(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request URL, and Telegram URLs contain the bot token.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    cfg = config_module.load()
    web = WebServer(cfg.port, cfg.webhook_secret)
    await web.start()

    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    try:
        await run(cfg, web)
    except asyncio.CancelledError:
        log.info("Stopping")
    finally:
        await web.stop()


if __name__ == "__main__":
    asyncio.run(main())
