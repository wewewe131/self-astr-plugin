import asyncio
import sqlite3

from core.constants import ALIAS_KV_KEY, KV_KEY
from services.storage_service import (
    ALIASES_TABLE,
    LEGACY_MIGRATION_KEY,
    META_TABLE,
    TIMEZONES_TABLE,
    StorageService,
)


def test_initialize_migrates_aliases_and_drops_legacy():
    async def _run():
        async def fake_get(key, default):
            if key == KV_KEY:
                return {"g1": {"u1": {"tz": "UTC+08:00", "name": "A"}}}
            if key == ALIAS_KV_KEY:
                return {
                    "owner1": {"u2": "老王", "u3": ""},
                    "owner2": "legacy-global-alias",
                }
            return default

        async def fake_put(key, value):
            return None

        svc = StorageService(fake_get, fake_put, auto_discover_sqlite=False)
        await svc.initialize()

        assert svc.data == {"g1": {"u1": {"tz": "UTC+08:00", "name": "A"}}}
        assert svc.aliases == {"owner1": {"u2": "老王"}}

    asyncio.run(_run())


def test_initialize_migrates_legacy_preferences_into_sqlite(tmp_path):
    async def _run():
        async def fake_get(key, default):
            if key == KV_KEY:
                return {
                    "g1": {
                        "u1": {"tz": "UTC+08:00", "name": "A"},
                        "u2": {"tz": "", "name": "skip"},
                    }
                }
            if key == ALIAS_KV_KEY:
                return {
                    "owner1": {"u2": "老王", "u3": ""},
                    "owner2": "legacy-global-alias",
                }
            return default

        async def fake_put(key, value):
            raise AssertionError("sqlite mode should not write back to legacy kv")

        db_path = tmp_path / "data_v4.db"
        svc = StorageService(fake_get, fake_put, sqlite_db_path=db_path)
        await svc.initialize()

        assert svc.data == {"g1": {"u1": {"tz": "UTC+08:00", "name": "A"}}}
        assert svc.aliases == {"owner1": {"u2": "老王"}}

        with sqlite3.connect(db_path) as conn:
            timezone_rows = conn.execute(
                f"SELECT group_id, user_id, tz, name FROM {TIMEZONES_TABLE}"
            ).fetchall()
            alias_rows = conn.execute(
                f"SELECT owner_id, target_id, alias FROM {ALIASES_TABLE}"
            ).fetchall()
            migration_flag = conn.execute(
                f"SELECT value FROM {META_TABLE} WHERE key = ?",
                (LEGACY_MIGRATION_KEY,),
            ).fetchone()

        assert timezone_rows == [("g1", "u1", "UTC+08:00", "A")]
        assert alias_rows == [("owner1", "u2", "老王")]
        assert migration_flag == ("done",)

    asyncio.run(_run())


def test_save_methods_persist_to_sqlite_and_reload(tmp_path):
    async def _run():
        async def fake_get(key, default):
            return default

        async def fake_put(key, value):
            raise AssertionError("sqlite mode should not write back to legacy kv")

        db_path = tmp_path / "data_v4.db"

        svc = StorageService(fake_get, fake_put, sqlite_db_path=db_path)
        await svc.initialize()
        svc.data = {"g9": {"u8": {"tz": "Asia/Shanghai", "name": "Tester"}}}
        svc.aliases = {"owner9": {"u8": "备注"}}
        await svc.save_timezones()
        await svc.save_aliases()

        reloaded = StorageService(fake_get, fake_put, sqlite_db_path=db_path)
        await reloaded.initialize()

        assert reloaded.data == {"g9": {"u8": {"tz": "Asia/Shanghai", "name": "Tester"}}}
        assert reloaded.aliases == {"owner9": {"u8": "备注"}}

    asyncio.run(_run())
