"""Event-bus abstraction: NATS in the cluster, an in-process bus for tests and the no-Docker demo."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

Handler = Callable[[dict], Awaitable[None]]
log = logging.getLogger("ttv.bus")


class MemoryBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    async def connect(self) -> None:
        return None

    async def publish(self, subject: str, event: dict) -> None:
        for handler in self._handlers.get(subject, []):
            await handler(event)

    async def subscribe(self, subject: str, handler: Handler) -> None:
        self._handlers.setdefault(subject, []).append(handler)

    async def close(self) -> None:
        self._handlers.clear()


class NatsBus:
    def __init__(self, url: str, retries: int = 60, delay: float = 2.0) -> None:
        self.url, self.retries, self.delay = url, retries, delay
        self._nc = None

    async def connect(self) -> None:
        import nats

        for attempt in range(1, self.retries + 1):
            try:
                self._nc = await nats.connect(self.url, connect_timeout=3, max_reconnect_attempts=-1)
                log.info("connected to %s", self.url)
                return
            except Exception as exc:
                log.warning("NATS not ready (%s), attempt %d/%d", exc, attempt, self.retries)
                await asyncio.sleep(self.delay)
        raise ConnectionError(f"could not reach NATS at {self.url}")

    async def publish(self, subject: str, event: dict) -> None:
        await self._nc.publish(subject, json.dumps(event).encode())

    async def subscribe(self, subject: str, handler: Handler) -> None:
        async def _cb(msg) -> None:
            try:
                await handler(json.loads(msg.data))
            except Exception:
                log.exception("dropping bad event")

        await self._nc.subscribe(subject, cb=_cb)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()


def make_bus(url: str) -> MemoryBus | NatsBus:
    return MemoryBus() if url == "memory" else NatsBus(url)
