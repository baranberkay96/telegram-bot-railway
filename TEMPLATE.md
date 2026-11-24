# TEMPLATE: Telegram Bot Starter (python-telegram-bot 22, Postgres)

Composer spec. `template.json` is the machine-readable copy.

## Services

| Field | Bot | Postgres |
|---|---|---|
| Source | repo `baranberkay96/telegram-bot-railway`, root `/services/bot` | `ghcr.io/railwayapp-templates/postgres-ssl:18.6@sha256:4fc833b4…` |
| Base / versions | `python:3.13.18-slim-trixie@sha256:6d68eb63…` (2026-11-24); python-telegram-bot 22.8, aiohttp 3.14.5, asyncpg 0.32.0, httpx 0.28.1, all transitive packages pinned | PostgreSQL 18.6 |
| Public domain | yes, target port 8080 (`POST /telegram` webhook, `/healthz`, `/`) | none |
| Healthcheck | `/healthz`, 300 s; 200 while the process runs, body = state | none (Railway base definition) |
| Restart | ALWAYS | ON_FAILURE (10) |
| Volume | none | `/var/lib/postgresql/data` |

Required input: `TELEGRAM_BOT_TOKEN`. Generated: `WEBHOOK_SECRET` (40 alphanumeric). Optional: `BOT_MODE` (webhook), `ADMIN_USER_IDS`, `TELEGRAM_API_URL`, `LOG_LEVEL` (INFO), `PORT` (8080), `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` (15). `DATABASE_URL` references `${{Postgres.DATABASE_URL}}`.

## Design

- `python -m app`: aiohttp server first (health 200 from the first second), then Postgres (backoff to 30 s, idempotent schema), then `Application.initialize()` (getMe checks the token), `setMyCommands`, `setWebhook(https://$RAILWAY_PUBLIC_DOMAIN/telegram, secret_token)`.
- Webhook calls: header compared with `hmac.compare_digest`; updates go to PTB's `update_queue`. 403 without the secret, 503 while the bot is not ready (Telegram retries).
- setWebhook failures (fresh domain not resolvable yet) retry 6× with backoff, then fall back to polling. No domain → polling from the start.
- Token missing → `not-configured`; Telegram 401/404 → `token-invalid`; both idle with a log line and never log the token (PTB's InvalidToken message contains it, httpx logs URLs with it: both suppressed). Network errors → retry with backoff. Never exits on configuration (STANDARD 8.29). Invalid `WEBHOOK_SECRET`/`BOT_MODE`/`ADMIN_USER_IDS`/`PORT` values fall back with a warning.
- Reminders: 10 s loop, due rows claimed with `FOR UPDATE SKIP LOCKED`, sent with `sendMessage`.
- SIGTERM: updater/application stop and shutdown, pool closed.

## Improvements over market templates

- Most-used market template (`aeither/telegram-bot-python`, telebot) polls, has no storage, healthcheck or pinned versions. The Postgres+Redis one (`codestorm-official/python-telegram-bot`) adds Redis that the bot does not need for its features. This one: webhook with secret header on the Railway domain, polling fallback, Postgres-backed notes/reminders, pinned dependencies, healthcheck.
- No crash-loop on a missing/wrong token; token never logged.
- Command menu set via `setMyCommands`.

## Resources

| Service | Idle RAM | Typical RAM | CPU |
|---|---|---|---|
| Bot | ≈60 MB (measured) | 80–150 MB | ≈0 idle |
| Postgres | ≈100 MB (measured) | 100–200 MB | ≈0 idle |

Estimated cost: about $1–2/month. Minimum plan: Trial.

## Verification checklist

- Default deploy with a placeholder token: Bot SUCCESS, `/healthz` 200 `ok token-invalid`, log explains the fix without the token, no restarts.
- `POST /telegram` without the secret header → 403.
- Local end-to-end run against a fake Bot API server (`TELEGRAM_API_URL`) and Postgres: `/start`, `/note`, `/notes`, `/delnote`, `/remind 2s` delivered, `/reminders`, `/cancel`, `/stats`, echo, webhook registration.
- With a real token (needs the user's BotFather token; not created by the agent): webhook set, `/start` answers in Telegram.

## Open questions

- A real Telegram login needs a token from the user; the agent tested the invalid-token path on Railway and the full command flow against a local fake Bot API.
