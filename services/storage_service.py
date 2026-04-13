from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

try:
    from ..core.constants import ALIAS_KV_KEY, KV_KEY
    from ..core.types import AliasData, TimezoneData
except ImportError:  # pragma: no cover - local direct-import fallback
    from core.constants import ALIAS_KV_KEY, KV_KEY
    from core.types import AliasData, TimezoneData

try:
    from astrbot.api import logger
except Exception:  # pragma: no cover - for local tests without astrbot
    logger = logging.getLogger(__name__)


class StorageService:
    def __init__(
        self,
        kv_getter: Callable[[str, object], Awaitable[object]],
        kv_putter: Callable[[str, object], Awaitable[None]],
    ):
        self._get_kv_data = kv_getter
        self._put_kv_data = kv_putter
        self._lock = asyncio.Lock()
        self.data: TimezoneData = {}
        self.aliases: AliasData = {}

    async def initialize(self) -> None:
        try:
            loaded = await self._get_kv_data(KV_KEY, {})
            self.data = loaded if isinstance(loaded, dict) else {}
        except Exception as e:
            logger.error(f"[time] failed to load kv data: {e}")
            self.data = {}

        try:
            loaded_alias = await self._get_kv_data(ALIAS_KV_KEY, {})
            migrated: AliasData = {}
            dropped_legacy = 0
            if isinstance(loaded_alias, dict):
                for owner, value in loaded_alias.items():
                    if isinstance(value, dict):
                        inner = {
                            str(tgt): str(alias)
                            for tgt, alias in value.items()
                            if alias
                        }
                        if inner:
                            migrated[str(owner)] = inner
                    else:
                        dropped_legacy += 1
            self.aliases = migrated
            if dropped_legacy:
                logger.warning(
                    f"[time] dropped {dropped_legacy} legacy global alias entries"
                )
        except Exception as e:
            logger.error(f"[time] failed to load alias data: {e}")
            self.aliases = {}

    async def save_timezones(self) -> None:
        async with self._lock:
            try:
                await self._put_kv_data(KV_KEY, self.data)
            except Exception as e:
                logger.error(f"[time] failed to save kv data: {e}")

    async def save_aliases(self) -> None:
        async with self._lock:
            try:
                await self._put_kv_data(ALIAS_KV_KEY, self.aliases)
            except Exception as e:
                logger.error(f"[time] failed to save alias data: {e}")
