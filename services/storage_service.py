from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path
from typing import Any

try:
    from ..core.types import UserInfo
except ImportError:  # pragma: no cover - local direct-import fallback
    from core.types import UserInfo


SQLITE_DB_NAME = "data_v4.db"
TIMEZONES_TABLE = "plugin_time_timezones"
ALIASES_TABLE = "plugin_time_aliases"


class StorageService:
    def __init__(self, sqlite_db_path: str | Path | None = None):
        self._db_path = self._resolve_db_path(sqlite_db_path)
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        await asyncio.to_thread(self._ensure_schema)

    async def list_timezones(
        self,
        group_id: str,
        viewer: str | None = None,
        target_uids: list[str] | None = None,
    ) -> dict[str, UserInfo]:
        if target_uids == []:
            return {}
        return await asyncio.to_thread(
            self._list_timezones,
            str(group_id),
            str(viewer or ""),
            [str(uid) for uid in target_uids] if target_uids is not None else None,
        )

    async def get_timezone(
        self,
        group_id: str,
        user_id: str,
        viewer: str | None = None,
    ) -> UserInfo | None:
        users = await self.list_timezones(group_id, viewer=viewer, target_uids=[user_id])
        return users.get(str(user_id))

    async def upsert_timezone(self, group_id: str, user_id: str, tz: str, name: str) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._upsert_timezone,
                str(group_id),
                str(user_id),
                str(tz),
                str(name),
            )

    async def delete_timezone(self, group_id: str, user_id: str) -> UserInfo | None:
        async with self._lock:
            return await asyncio.to_thread(
                self._delete_timezone,
                str(group_id),
                str(user_id),
            )

    async def clear_group_timezones(self, group_id: str) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._clear_group_timezones, str(group_id))

    async def list_aliases(
        self,
        owner_id: str,
        target_uids: list[str] | None = None,
    ) -> dict[str, str]:
        if target_uids == []:
            return {}
        return await asyncio.to_thread(
            self._list_aliases,
            str(owner_id),
            [str(uid) for uid in target_uids] if target_uids is not None else None,
        )

    async def set_alias(self, owner_id: str, target_id: str, alias: str) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._set_alias,
                str(owner_id),
                str(target_id),
                str(alias),
            )

    async def delete_aliases(self, owner_id: str, target_uids: list[str]) -> dict[str, str]:
        async with self._lock:
            return await asyncio.to_thread(
                self._delete_aliases,
                str(owner_id),
                [str(uid) for uid in target_uids],
            )

    async def clear_aliases(self, owner_id: str) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._clear_aliases, str(owner_id))

    def _resolve_db_path(self, sqlite_db_path: str | Path | None) -> Path:
        if sqlite_db_path:
            return Path(sqlite_db_path).expanduser().resolve()

        env_path = os.getenv("ASTRBOT_DATA_DB_PATH")
        if env_path:
            return Path(env_path).expanduser().resolve()

        current = Path(__file__).resolve()
        for parent in current.parents:
            candidate = parent / SQLITE_DB_NAME
            if candidate.exists():
                return candidate

        raise RuntimeError("data_v4.db not found, please set ASTRBOT_DATA_DB_PATH")

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self._db_path, timeout=30)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {TIMEZONES_TABLE} (
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    tz TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (group_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS {ALIASES_TABLE} (
                    owner_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    PRIMARY KEY (owner_id, target_id)
                );
                """
            )

    def _list_timezones(
        self,
        group_id: str,
        viewer: str,
        target_uids: list[str] | None,
    ) -> dict[str, UserInfo]:
        params: list[Any] = [viewer, group_id]
        sql = f"""
            SELECT t.user_id, t.tz, t.name, a.alias
            FROM {TIMEZONES_TABLE} AS t
            LEFT JOIN {ALIASES_TABLE} AS a
              ON a.owner_id = ?
             AND a.target_id = t.user_id
            WHERE t.group_id = ?
        """
        if target_uids:
            placeholders = ", ".join("?" for _ in target_uids)
            sql += f" AND t.user_id IN ({placeholders})"
            params.extend(target_uids)
        sql += " ORDER BY t.user_id"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        result: dict[str, UserInfo] = {}
        for user_id, tz, name, alias in rows:
            info: UserInfo = {"tz": str(tz), "name": str(name or "")}
            if alias:
                info["alias"] = str(alias)
            result[str(user_id)] = info
        return result

    def _upsert_timezone(self, group_id: str, user_id: str, tz: str, name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {TIMEZONES_TABLE} (group_id, user_id, tz, name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(group_id, user_id)
                DO UPDATE SET tz = excluded.tz, name = excluded.name
                """,
                (group_id, user_id, tz, name),
            )

    def _delete_timezone(self, group_id: str, user_id: str) -> UserInfo | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT tz, name
                FROM {TIMEZONES_TABLE}
                WHERE group_id = ? AND user_id = ?
                """,
                (group_id, user_id),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                f"DELETE FROM {TIMEZONES_TABLE} WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            )

        return {"tz": str(row[0]), "name": str(row[1] or "")}

    def _clear_group_timezones(self, group_id: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                f"DELETE FROM {TIMEZONES_TABLE} WHERE group_id = ?",
                (group_id,),
            )
        return int(cur.rowcount or 0)

    def _list_aliases(self, owner_id: str, target_uids: list[str] | None) -> dict[str, str]:
        params: list[Any] = [owner_id]
        sql = f"SELECT target_id, alias FROM {ALIASES_TABLE} WHERE owner_id = ?"
        if target_uids:
            placeholders = ", ".join("?" for _ in target_uids)
            sql += f" AND target_id IN ({placeholders})"
            params.extend(target_uids)
        sql += " ORDER BY target_id"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {str(target_id): str(alias) for target_id, alias in rows}

    def _set_alias(self, owner_id: str, target_id: str, alias: str) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {ALIASES_TABLE} (owner_id, target_id, alias)
                VALUES (?, ?, ?)
                ON CONFLICT(owner_id, target_id)
                DO UPDATE SET alias = excluded.alias
                """,
                (owner_id, target_id, alias),
            )

    def _delete_aliases(self, owner_id: str, target_uids: list[str]) -> dict[str, str]:
        if not target_uids:
            return {}

        placeholders = ", ".join("?" for _ in target_uids)
        params = [owner_id, *target_uids]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT target_id, alias
                FROM {ALIASES_TABLE}
                WHERE owner_id = ?
                  AND target_id IN ({placeholders})
                """,
                params,
            ).fetchall()
            if not rows:
                return {}
            conn.execute(
                f"""
                DELETE FROM {ALIASES_TABLE}
                WHERE owner_id = ?
                  AND target_id IN ({placeholders})
                """,
                params,
            )

        return {str(target_id): str(alias) for target_id, alias in rows}

    def _clear_aliases(self, owner_id: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                f"DELETE FROM {ALIASES_TABLE} WHERE owner_id = ?",
                (owner_id,),
            )
        return int(cur.rowcount or 0)
