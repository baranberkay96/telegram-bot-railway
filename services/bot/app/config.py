"""Settings from environment variables.

Values typed into Railway's deploy form must never stop the service: an
invalid value falls back to its default with a warning in the log.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
from dataclasses import dataclass

log = logging.getLogger("bot.config")

DEFAULT_PORT = 8080
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
SECRET_CHARS = re.compile(r"^[A-Za-z0-9_-]{16,256}$")  # what Telegram accepts, at least 16 long
DOMAIN = re.compile(r"^[A-Za-z0-9.-]+(:\d+)?$")


@dataclass(frozen=True)
class Config:
    token: str
    database_url: str
    mode: str  # "webhook" or "polling"
    public_domain: str
    webhook_secret: str
    port: int
    admin_ids: frozenset[int]
    api_url: str  # empty: api.telegram.org


def _port() -> int:
    value = os.environ.get("PORT", "").strip()
    if value.isdigit() and 1 <= int(value) <= 65535:
        return int(value)
    if value:
        log.warning("PORT=%r is not a port number; using %s", value, DEFAULT_PORT)
    return DEFAULT_PORT


def _token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
    if token.lower().startswith("bot") and token[3:].split(":", 1)[0].isdigit():
        token = token[3:]  # pasted from an API URL ("bot123456:ABC...")
    return token


def _domain() -> str:
    value = os.environ.get("WEBHOOK_DOMAIN", "").strip() or os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    value = value.removeprefix("https://").removeprefix("http://").rstrip("/")
    if value and not DOMAIN.match(value):
        log.warning("Webhook domain %r is not a host name; ignoring it", value)
        return ""
    return value


def _mode(domain: str) -> str:
    value = os.environ.get("BOT_MODE", "webhook").strip().lower()
    if value not in ("webhook", "polling"):
        log.warning("BOT_MODE=%r is neither webhook nor polling; using webhook", value)
        value = "webhook"
    if value == "webhook" and not domain:
        log.warning("Webhook mode needs a public domain (Settings, Networking, Generate Domain); using polling")
        value = "polling"
    return value


def _secret() -> str:
    value = os.environ.get("WEBHOOK_SECRET", "").strip()
    if SECRET_CHARS.match(value):
        return value
    if value:
        log.warning("WEBHOOK_SECRET must be 16-256 characters of A-Z a-z 0-9 _ -; using a random one")
    return secrets.token_urlsafe(32)  # still safe: it is sent to Telegram at every start


def _admin_ids() -> frozenset[int]:
    ids = set()
    for part in re.split(r"[,\s]+", os.environ.get("ADMIN_USER_IDS", "").strip()):
        if part.isdigit():
            ids.add(int(part))
        elif part:
            log.warning("ADMIN_USER_IDS: %r is not a numeric Telegram user id; skipped", part)
    return frozenset(ids)


def _api_url() -> str:
    value = os.environ.get("TELEGRAM_API_URL", "").strip().rstrip("/")
    if value and not re.match(r"^https?://[^\s/]+(/[^\s]*)?$", value):
        log.warning("TELEGRAM_API_URL=%r is not an http(s) URL; using api.telegram.org", value)
        return ""
    return value


def log_level() -> str:
    value = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    return value if value in LOG_LEVELS else "INFO"


def load() -> Config:
    domain = _domain()
    return Config(
        token=_token(),
        database_url=os.environ.get("DATABASE_URL", "").strip(),
        mode=_mode(domain),
        public_domain=domain,
        webhook_secret=_secret(),
        port=_port(),
        admin_ids=_admin_ids(),
        api_url=_api_url(),
    )
