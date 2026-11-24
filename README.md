# Deploy and Host Telegram Bot Starter with Railway

A Python Telegram bot that works as soon as you paste the token from @BotFather: it registers its own webhook on the Railway domain, answers commands for notes and reminders, and keeps its data in Postgres. Built on python-telegram-bot 22. It is a starter: eject the repo and add your own handlers.

## About Hosting Telegram Bot Starter

Telegram delivers messages to bots either by long polling or by calling a webhook URL. Webhooks are the efficient choice for an always-on bot, but they need a public HTTPS address, a secret so nobody else can post fake updates, and a process that stays up. This community template gives the bot a Railway domain, sets the webhook to `https://{your-domain}/telegram` at every start, checks Telegram's secret header on every call, and falls back to polling when there is no domain. State lives in a Railway Postgres on the private network; tables are created on first start. A `/healthz` endpoint answers Railway's healthcheck, and a missing or wrong token is logged clearly (never the token itself) instead of crash-looping.

## Common Use Cases

- A personal or team assistant bot with notes and reminders
- A starting point for your own bot: customer support, notifications from your apps, small games
- A bot that calls other services in your Railway project over the private network
- Learning python-telegram-bot with webhooks, storage and health checks already wired up

## Dependencies for Telegram Bot Starter Hosting

- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- The Bot service (built from this repo, Python 3.13, python-telegram-bot 22.8, aiohttp, asyncpg) with a public domain
- Postgres 18 (Railway's `postgres-ssl` image) with a volume

### Deployment Dependencies

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [python-telegram-bot documentation](https://docs.python-telegram-bot.org/en/stable/)
- [python-telegram-bot on GitHub](https://github.com/python-telegram-bot/python-telegram-bot)
- [Telegram Bot Platform terms](https://telegram.org/tos/bot-developers)
- [Railway Fair Use Policy](https://railway.com/legal/fair-use)

### Implementation Details

| Service | What runs inside | Volume | Port |
|---|---|---|---|
| Bot | python-telegram-bot 22.8 application behind an aiohttp server: `POST /telegram` (webhook), `/healthz` | none | 8080, public domain |
| Postgres | PostgreSQL 18 (chats, notes, reminders) | `/var/lib/postgresql/data` | 5432, private |

**First start**

1. In Telegram, open [@BotFather](https://t.me/BotFather), send `/newbot`, pick a name and a username, and copy the token.
2. Paste it into `TELEGRAM_BOT_TOKEN` when you deploy (or later on the Bot service, then redeploy).
3. The deploy log prints `Webhook set to https://...` and `Bot @yourbot is running in webhook mode`. Open your bot in Telegram and send `/start`.

**Commands included**

| Command | What it does |
|---|---|
| `/start`, `/help` | Greeting and the command list (also shown in Telegram's menu button) |
| `/note text`, `/notes`, `/delnote id` | Notes per chat, stored in Postgres |
| `/remind 10m text`, `/reminders`, `/cancel id` | Reminders after `10m`, `1h30m`, `2d`, `1w` (up to 365 days, 25 per user); survive redeploys |
| `/id` | The chat id and your user id |
| `/ping` | Bot and database status |
| `/stats` | Chat, note and reminder counts, only for users listed in `ADMIN_USER_IDS` |

Plain text in a private chat is echoed back: that handler (`echo` in `app/handlers.py`) is the place for your own logic.

**Webhook, polling and security**

`BOT_MODE=webhook` (default) needs the service's public domain; Railway creates it with the template. Only requests carrying the generated `WEBHOOK_SECRET` header are accepted; everything else gets 403. If Telegram cannot reach the domain after several tries, or there is no domain, the bot switches to polling and keeps working. `BOT_MODE=polling` forces polling. Only one deployment may use a token at a time: Telegram allows either one webhook or one poller per bot.

**When something is wrong**

If `TELEGRAM_BOT_TOKEN` is empty or Telegram rejects it, the service stays up, `/healthz` reports `not-configured` or `token-invalid`, and the log says what to do. Fix the variable and redeploy. The token never appears in the log (request URL logging is switched off because Telegram URLs contain it).

**Extend it**

The deployed code comes from this template's GitHub repo. To change it, use **Eject** in the Bot service's settings (Railway copies the repo to your GitHub account and deploys from it), then add handlers in `register()` in `app/handlers.py` and tables in `SCHEMA` in `app/db.py`. The database pool is `context.bot_data["pool"]`. Pushing to your repo redeploys. `TELEGRAM_API_URL` points the bot at a self-hosted Bot API server if you run one.

**Scaling and versions**

Run one replica: Telegram sends each update once, and reminders are claimed with row locks, but polling allows only one poller. Versions are pinned in `services/bot/requirements.txt` and the Dockerfile (`python:3.13.18-slim-trixie` by digest); change them there to upgrade.

**Resources**

Measured on Railway: the bot idles at about 60 MB RAM and Postgres at about 100 MB, near 0 vCPU. Trial plan is enough; cost is roughly $1–2/month.

**Not included, on purpose**

No MTProto/MTProxy, no userbots (user-account automation), no proxy features, no mass messaging: they break Telegram's or Railway's terms.

### Why Deploy Telegram Bot Starter on Railway?

Railway gives the bot an HTTPS domain for its webhook, keeps it online, and puts a private Postgres in the same project, with logs and Git redeploys in one place. Paste a token and you have a working bot to build on. This is a community template, not affiliated with Telegram or the python-telegram-bot project.
