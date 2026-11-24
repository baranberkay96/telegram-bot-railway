"""HTTP server: Railway's /healthz and the Telegram webhook endpoint.

/healthz answers 200 while the process runs, also when the token is missing
or wrong (the log says what to fix), so a configuration problem never fails
the deploy. POST /telegram accepts updates only with the secret header that
was registered with Telegram.
"""
from __future__ import annotations

import hmac
import json
import logging
import time
from collections.abc import Awaitable, Callable

from aiohttp import web

log = logging.getLogger("bot.web")

WEBHOOK_PATH = "/telegram"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
UpdateHandler = Callable[[dict], Awaitable[None]]


class WebServer:
    def __init__(self, port: int, secret: str) -> None:
        self._port = port
        self._secret = secret
        self._state, self._detail, self._since = "starting", "", time.time()
        self._handler: UpdateHandler | None = None
        self._runner: web.AppRunner | None = None

    def set_state(self, state: str, detail: str = "") -> None:
        if (state, detail) != (self._state, self._detail):
            self._state, self._detail, self._since = state, detail, time.time()

    def set_update_handler(self, handler: UpdateHandler | None) -> None:
        self._handler = handler

    async def _health(self, request: web.Request) -> web.Response:
        if request.query.get("format") == "json":
            return web.json_response(
                {"status": "ok", "state": self._state, "detail": self._detail, "since": int(self._since)}
            )
        return web.Response(text=f"ok {self._state}\n")

    async def _index(self, _: web.Request) -> web.Response:
        return web.Response(text="Telegram bot is running. Talk to it in Telegram.\n")

    async def _webhook(self, request: web.Request) -> web.Response:
        given = request.headers.get(SECRET_HEADER, "")
        if not hmac.compare_digest(given.encode(), self._secret.encode()):
            return web.Response(status=403, text="forbidden\n")
        if self._handler is None:
            return web.Response(status=503, text="bot not ready\n")  # Telegram retries later
        try:
            data = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.Response(status=400, text="bad request\n")
        if not isinstance(data, dict):
            return web.Response(status=400, text="bad request\n")
        await self._handler(data)
        return web.Response(text="ok\n")

    async def start(self) -> None:
        app = web.Application(client_max_size=2 * 1024 * 1024)
        app.router.add_get("/healthz", self._health)
        app.router.add_get("/", self._index)
        app.router.add_post(WEBHOOK_PATH, self._webhook)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        # host=None binds every interface (IPv4 and IPv6) as separate sockets.
        await web.TCPSite(self._runner, host=None, port=self._port).start()
        log.info("HTTP server listening on port %s (/healthz, POST %s)", self._port, WEBHOOK_PATH)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
