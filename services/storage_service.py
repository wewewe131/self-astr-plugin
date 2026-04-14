from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from pathlib import Path
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


SQLITE_DB_NAME = "data_v4.db"
TIMEZONES_TABLE = "plugin_time_timezones"
ALIASES_TABLE = "plugin_time_aliases"
META_TABLE = "plugin_time_meta"
LEGACY_MIGRATION_KEY = "legacy_preferences_v1"


class StorageService:
    def __init__(
        self,
        kv_getter: Callable[[str, object], Awaitable[object]],
        kv_putter: Callable[[str, object], Awaitable[None]],
        sqlite_db_path: str | Path | None = None,
        auto_discover_sqlite: bool = True,
    ):
        self._get_kv_data = kv_getter
        self._put_kv_data = kv_putter
        self._lock = asyncio.Lock()
        self._sqlite_db_path = self._resolve_sqlite_db_path(
            sqlite_db_path,
            auto_discover_sqlite=auto_discover_sqlite,
        )
        self.data: TimezoneData = {}
        self.aliases: AliasData = {}

    async def initialize(self) -> None:
        if self._sqlite_db_path:
            try:
                await self._initialize_from_sqlite()
                return
            except Exception as e:
                logger.error(f"[time] failed to initialize sqlite storage: {e}")

        await self._initialize_from_kv()

    async def _initialize_from_kv(self) -> None:
        try:
            loaded = await self._get_kv_data(KV_KEY, {})
            self.data = self._normalize_timezones(loaded)
        except Exception as e:
            logger.error(f"[time] failed to load kv data: {e}")
            self.data = {}

        try:
            loaded_alias = await self._get_kv_data(ALIAS_KV_KEY, {})
            self.aliases = self._normalize_aliases(loaded_alias)
        except Exception as e:
            logger.error(f"[time] failed to load alias data: {e}")
            self.aliases = {}

    async def _initialize_from_sqlite(self) -> None:
        await asyncio.to_thread(self._ensure_sqlite_schema)
        migration_plan = await asyncio.to_thread(self._get_sqlite_migration_plan)

        if not migration_plan["legacy_migrated"]:
            legacy_timezones: TimezoneData | None = None
            legacy_aliases: AliasData | None = None

            if not migration_plan["has_timezones"]:
                legacy_timezones = await self._load_legacy_timezones()
            if not migration_plan["has_aliases"]:
                legacy_aliases = await self._load_legacy_aliases()

            # Mark the migration as completed so clearing data later will not
            # accidentally re-import stale JSON from AstrBot preferences.
            await asyncio.to_thread(
                self._migrate_legacy_preferences_to_sqlite,
                legacy_timezones,
                legacy_aliases,
            )

        self.data, self.aliases = await asyncio.to_thread(self._load_sqlite_state)

    async def save_timezones(self) -> None:
        async with self._lock:
            try:
                if self._sqlite_db_path:
                    await asyncio.to_thread(self._save_timezones_sqlite, self.data)
                    return
                await self._put_kv_data(KV_KEY, self.data)
            except Exception as e:
                logger.error(f"[time] failed to save kv data: {e}")

    async def save_aliases(self) -> None:
        async with self._lock:
            try:
                if self._sqlite_db_path:
                    await asyncio.to_thread(self._save_aliases_sqlite, self.aliases)
                    return
                await self._put_kv_data(ALIAS_KV_KEY, self.aliases)
            except Exception as e:
                logger.error(f"[time] failed to save alias data: {e}")

    def _resolve_sqlite_db_path(
        self,
        sqlite_db_path: str | Path | None,
        auto_discover_sqlite: bool,
    ) -> Path | None:
        if sqlite_db_path:
            return Path(sqlite_db_path).expanduser().resolve()
        if not auto_discover_sqlite:
            return None

        env_path = os.getenv("ASTRBOT_DATA_DB_PATH")
        if env_path:
            return Path(env_path).expanduser().resolve()

        current = Path(__file__).resolve()
        for parent in current.parents:
            candidate = parent / SQLITE_DB_NAME
            if candidate.exists():
                return candidate
        return None

    def _connect_sqlite(self) -> sqlite3.Connection:
        if not self._sqlite_db_path:
            raise RuntimeError("sqlite storage is not configured")
        self._sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self._sqlite_db_path, timeout=30)

    def _ensure_sqlite_schema(self) -> None:
        with self._connect_sqlite() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TIMEZONES_TABLE} (
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    tz TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (group_id, user_id)
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {ALIASES_TABLE} (
                    owner_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    PRIMARY KEY (owner_id, target_id)
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {META_TABLE} (
                    key TEXT NOT NULL PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _get_sqlite_migration_plan(self) -> dict[str, bool]:
        with self._connect_sqlite() as conn:
            legacy_migrated = self._get_meta_value(conn, LEGACY_MIGRATION_KEY) == "done"
            has_timezones = (
                conn.execute(f"SELECT 1 FROM {TIMEZONES_TABLE} LIMIT 1").fetchone()
                is not None
            )
            has_aliases = (
                conn.execute(f"SELECT 1 FROM {ALIASES_TABLE} LIMIT 1").fetchone()
                is not None
            )
        return {
            "legacy_migrated": legacy_migrated,
            "has_timezones": has_timezones,
            "has_aliases": has_aliases,
        }

    def _get_meta_value(self, conn: sqlite3.Connection, key: str) -> str | None:
        row = conn.execute(
            f"SELECT value FROM {META_TABLE} WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row[0]) if row else None

    def _set_meta_value(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            f"""
            INSERT INTO {META_TABLE} (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    async def _load_legacy_timezones(self) -> TimezoneData:
        try:
            loaded = await self._get_kv_data(KV_KEY, {})
        except Exception as e:
            logger.error(f"[time] failed to load legacy timezone data: {e}")
            return {}
        return self._normalize_timezones(loaded)

    async def _load_legacy_aliases(self) -> AliasData:
        try:
            loaded_alias = await self._get_kv_data(ALIAS_KV_KEY, {})
        except Exception as e:
            logger.error(f"[time] failed to load legacy alias data: {e}")
            return {}
        return self._normalize_aliases(loaded_alias)

    def _migrate_legacy_preferences_to_sqlite(
        self,
        legacy_timezones: TimezoneData | None,
        legacy_aliases: AliasData | None,
    ) -> None:
        with self._connect_sqlite() as conn:
            if legacy_timezones and not conn.execute(
                f"SELECT 1 FROM {TIMEZONES_TABLE} LIMIT 1"
            ).fetchone():
                conn.executemany(
                    f"""
                    INSERT INTO {TIMEZONES_TABLE} (group_id, user_id, tz, name)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (
                            str(group_id),
                            str(user_id),
                            info["tz"],
                            str(info.get("name") or ""),
                        )
                        for group_id, members in legacy_timezones.items()
                        for user_id, info in members.items()
                    ],
                )

            if legacy_aliases and not conn.execute(
                f"SELECT 1 FROM {ALIASES_TABLE} LIMIT 1"
            ).fetchone():
                conn.executemany(
                    f"""
                    INSERT INTO {ALIASES_TABLE} (owner_id, target_id, alias)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (str(owner_id), str(target_id), alias)
                        for owner_id, targets in legacy_aliases.items()
                        for target_id, alias in targets.items()
                    ],
                )

            self._set_meta_value(conn, LEGACY_MIGRATION_KEY, "done")
            conn.commit()

    def _load_sqlite_state(self) -> tuple[TimezoneData, AliasData]:
        with self._connect_sqlite() as conn:
            timezone_rows = conn.execute(
                f"""
                SELECT group_id, user_id, tz, name
                FROM {TIMEZONES_TABLE}
                ORDER BY group_id, user_id
                """
            ).fetchall()
            alias_rows = conn.execute(
                f"""
                SELECT owner_id, target_id, alias
                FROM {ALIASES_TABLE}
                ORDER BY owner_id, target_id
                """
            ).fetchall()

        data: TimezoneData = {}
        for group_id, user_id, tz, name in timezone_rows:
            data.setdefault(str(group_id), {})[str(user_id)] = {
                "tz": str(tz),
                "name": str(name or ""),
            }

        aliases: AliasData = {}
        for owner_id, target_id, alias in alias_rows:
            aliases.setdefault(str(owner_id), {})[str(target_id)] = str(alias)

        return data, aliases

    def _save_timezones_sqlite(self, data: TimezoneData) -> None:
        normalized = self._normalize_timezones(data)
        with self._connect_sqlite() as conn:
            conn.execute(f"DELETE FROM {TIMEZONES_TABLE}")
            conn.executemany(
                f"""
                INSERT INTO {TIMEZONES_TABLE} (group_id, user_id, tz, name)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        str(group_id),
                        str(user_id),
                        info["tz"],
                        str(info.get("name") or ""),
                    )
                    for group_id, members in normalized.items()
                    for user_id, info in members.items()
                ],
            )
            conn.commit()

    def _save_aliases_sqlite(self, aliases: AliasData) -> None:
        normalized = self._normalize_aliases(aliases)
        with self._connect_sqlite() as conn:
            conn.execute(f"DELETE FROM {ALIASES_TABLE}")
            conn.executemany(
                f"""
                INSERT INTO {ALIASES_TABLE} (owner_id, target_id, alias)
                VALUES (?, ?, ?)
                """,
                [
                    (str(owner_id), str(target_id), alias)
                    for owner_id, targets in normalized.items()
                    for target_id, alias in targets.items()
                ],
            )
            conn.commit()

    def _normalize_timezones(self, loaded: object) -> TimezoneData:
        migrated: TimezoneData = {}
        if not isinstance(loaded, dict):
            return migrated

        for group_id, members in loaded.items():
            if not isinstance(members, dict):
                continue

            group_entries = {}
            for user_id, info in members.items():
                if not isinstance(info, dict):
                    continue
                tz = str(info.get("tz") or "").strip()
                if not tz:
                    continue
                group_entries[str(user_id)] = {
                    "tz": tz,
                    "name": str(info.get("name") or ""),
                }

            if group_entries:
                migrated[str(group_id)] = group_entries

        return migrated

    def _normalize_aliases(self, loaded_alias: object) -> AliasData:
        migrated: AliasData = {}
        dropped_legacy = 0
        if not isinstance(loaded_alias, dict):
            return migrated

        for owner, value in loaded_alias.items():
            if isinstance(value, dict):
                inner = {
                    str(tgt): str(alias)
                    for tgt, alias in value.items()
                    if str(alias).strip()
                }
                if inner:
                    migrated[str(owner)] = inner
            else:
                dropped_legacy += 1

        if dropped_legacy:
            logger.warning(
                f"[time] dropped {dropped_legacy} legacy global alias entries"
            )

        return migrated
