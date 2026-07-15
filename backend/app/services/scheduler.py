"""Optional scheduled background sync (settings-driven: enabled flag +
interval, default 15 min). Started from the app lifespan; each tick re-reads
settings so changes take effect without a restart."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..database import SessionLocal
from . import settings_service
from .jira import sync_service
from .jira.factory import get_adapter

logger = logging.getLogger("pact.scheduler")

_CHECK_EVERY_SECONDS = 30


class SyncScheduler:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._last_run: datetime | None = None

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=_CHECK_EVERY_SECONDS)
                break  # stop requested
            except asyncio.TimeoutError:
                pass  # normal tick
            try:
                await self._tick()
            except Exception:  # never let one bad sync kill the loop
                logger.exception("scheduled sync failed")

    async def _tick(self) -> None:
        async with SessionLocal() as session:
            cfg = await settings_service.get_all(session)
            sync_cfg = cfg.get("sync", {})
            if not sync_cfg.get("enabled"):
                return
            interval = max(1, int(sync_cfg.get("interval_minutes", 15)))
            now = datetime.now(timezone.utc)
            if self._last_run and now - self._last_run < timedelta(minutes=interval):
                return
            adapter = await get_adapter(session)
            result = await sync_service.sync_from_jira(
                session, adapter, actor="scheduled-sync"
            )
            await session.commit()
            self._last_run = now
            logger.info("scheduled sync completed: %s", result.as_dict())


scheduler = SyncScheduler()
