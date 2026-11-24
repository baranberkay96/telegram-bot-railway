# NOTICE: Telegram Bot Starter template

This is a community template. It is not made, endorsed or supported by Telegram, the python-telegram-bot project or Railway. Telegram is a trademark of Telegram Group Inc.

## Components

| Component | Source | License | How it is used |
|---|---|---|---|
| python-telegram-bot 22.8 | https://github.com/python-telegram-bot/python-telegram-bot | LGPL-3.0-only | Installed unmodified from PyPI and used as a library; its source is available at the link |
| httpx 0.28.1, httpcore, anyio, h11, certifi, idna | PyPI | BSD-3-Clause / MIT / MPL-2.0 (certifi) | Dependencies of python-telegram-bot |
| aiohttp 3.14.5 and its dependencies (aiohappyeyeballs, aiosignal, attrs, frozenlist, multidict, propcache, yarl) | PyPI | Apache-2.0 / MIT | Webhook and health HTTP server |
| asyncpg 0.32.0 | https://github.com/MagicStack/asyncpg | Apache-2.0 | Postgres driver |
| typing_extensions | PyPI | PSF-2.0 | Dependency |
| Python 3.13.18 (`python:3.13.18-slim-trixie@sha256:6d68eb6310a906f26c7638eb6ea7557d4261662df3181af2f80f1f9a7e34c549`) | https://hub.docker.com/_/python | PSF License; Debian packages under their own licenses | Base image |
| PostgreSQL 18.6 (`ghcr.io/railwayapp-templates/postgres-ssl:18.6`) | https://github.com/railwayapp-templates/postgres-ssl | PostgreSQL License | Database service, Railway's standard definition |

## Files written for this template

Everything under `services/bot/` (the bot code, Dockerfile, requirements) and the documentation was written for this template and is offered under the MIT License. You may copy and change it for your own bots. python-telegram-bot stays under its own LGPL-3.0 license; replacing or modifying it is possible by changing `requirements.txt`.

## Upstream files checked

- python-telegram-bot v22.8: `src/telegram/_bot.py` (`initialize` raising `InvalidToken` with the token in the message, `set_webhook(secret_token=...)`), `src/telegram/request/_baserequest.py`, the "custom webhook bot" approach from the project's examples (re-implemented with aiohttp, not copied).
- Telegram Bot API: `setWebhook` (`secret_token`, `X-Telegram-Bot-Api-Secret-Token`), `setMyCommands`, `getMe`.
- PyPI metadata of every pinned package (2026-11-24).

## Market templates

The three Telegram bot templates on the Railway marketplace (`aeither/telegram-bot-python`, `codestorm-official/python-telegram-bot`, `dangos-dev/TelegramBot.Webhook`) were reviewed for features only. No files or text were copied.

## Terms

Bots must follow Telegram's terms for bot developers. Userbots, MTProto proxies, spam and mass messaging are not part of this template and are not allowed by Railway's Fair Use Policy.
