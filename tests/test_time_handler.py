import asyncio
from types import SimpleNamespace

from handlers.time_handler import TimeCommandHandler
from services.storage_service import StorageService
from services.time_service import TimeService


class FakeRenderService:
    def render_entries(self, event, entries, header, display_name_fn, viewer=None):
        return [f"{header}:{len(entries)}"]


class MsgObj:
    def __init__(self, self_id="", sender=None):
        self.self_id = self_id
        self.raw_message = {
            "self_id": self_id,
            "sender": sender or {},
        }


class FakeEvent:
    def __init__(
        self,
        message_str,
        group_id=None,
        sender_id="1000",
        sender_name="tester",
        admin=False,
        platform="aiocqhttp",
        messages=None,
        group_members=None,
        sender_card=None,
    ):
        self.message_str = message_str
        self._group_id = group_id
        self._sender_id = sender_id
        self._sender_name = sender_name
        self._admin = admin
        self._platform = platform
        self._messages = messages or []
        self._group_members = group_members or {}
        self.message_obj = MsgObj(
            sender={
                "card": sender_card or "",
                "nickname": sender_name,
            }
        )

    def get_group_id(self):
        return self._group_id

    def get_sender_id(self):
        return self._sender_id

    def get_sender_name(self):
        return self._sender_name

    def get_platform_name(self):
        return self._platform

    def get_messages(self):
        return self._messages

    def is_admin(self):
        return self._admin

    async def get_group(self, group_id=None, **kwargs):
        members = [
            SimpleNamespace(
                user_id=uid,
                card=member[0] if isinstance(member, tuple) else member,
                nickname=member[1] if isinstance(member, tuple) else member,
            )
            for uid, member in self._group_members.items()
        ]
        return SimpleNamespace(members=members)

    def plain_result(self, text):
        return text

    def chain_result(self, chain):
        return chain


async def _collect(async_gen):
    return [item async for item in async_gen]


def test_time_route_unknown_subcommand(tmp_path):
    async def _run():
        storage = StorageService(sqlite_db_path=tmp_path / "data_v4.db")
        await storage.initialize()
        handler = TimeCommandHandler(storage, TimeService(), FakeRenderService())

        event = FakeEvent("/time what", group_id="g1")
        result = await _collect(handler.handle(event))
        assert len(result) == 1
        assert "未知子命令：what" in result[0]

    asyncio.run(_run())


def test_time_requires_group_for_default_show(tmp_path):
    async def _run():
        storage = StorageService(sqlite_db_path=tmp_path / "data_v4.db")
        await storage.initialize()
        handler = TimeCommandHandler(storage, TimeService(), FakeRenderService())

        event = FakeEvent("/time")
        result = await _collect(handler.handle(event))
        assert result == ["该指令只能在群组中使用"]

    asyncio.run(_run())


def test_time_set_and_list_routes(tmp_path):
    async def _run():
        storage = StorageService(sqlite_db_path=tmp_path / "data_v4.db")
        await storage.initialize()
        handler = TimeCommandHandler(storage, TimeService(), FakeRenderService())

        set_evt = FakeEvent(
            "/time set +8",
            group_id="g1",
            sender_id="u1",
            sender_name="用户名",
            sender_card="当前群名片",
            group_members={"u1": ("", "用户名")},
        )
        set_result = await _collect(handler.handle(set_evt))
        assert "已登记 当前群名片 的时区为 UTC+08:00" in set_result[0]

        list_evt = FakeEvent(
            "/time list",
            group_id="g1",
            sender_id="u1",
            sender_name="用户名",
            sender_card="当前群名片",
            group_members={"u1": ("", "用户名")},
        )
        list_result = await _collect(handler.handle(list_evt))
        assert "本群已登记 1 人" in list_result[0]
        assert "当前群名片" in list_result[0]

    asyncio.run(_run())


def test_time_does_not_fallback_to_username_when_card_is_blank(tmp_path):
    async def _run():
        storage = StorageService(sqlite_db_path=tmp_path / "data_v4.db")
        await storage.initialize()
        handler = TimeCommandHandler(storage, TimeService(), FakeRenderService())

        set_evt = FakeEvent(
            "/time set +8",
            group_id="g1",
            sender_id="u1",
            sender_name="用户名",
            sender_card="",
            group_members={"u1": ("", "用户名")},
        )
        set_result = await _collect(handler.handle(set_evt))
        assert "已登记 u1 的时区为 UTC+08:00" in set_result[0]
        assert "用户名" not in set_result[0]

        list_evt = FakeEvent(
            "/time list",
            group_id="g1",
            sender_id="u1",
            sender_name="用户名",
            sender_card="",
            group_members={"u1": ("", "用户名")},
        )
        list_result = await _collect(handler.handle(list_evt))
        assert "u1" in list_result[0]
        assert "用户名" not in list_result[0]

    asyncio.run(_run())


def test_time_list_prefers_alias_over_group_card(tmp_path):
    async def _run():
        storage = StorageService(sqlite_db_path=tmp_path / "data_v4.db")
        await storage.initialize()
        await storage.upsert_timezone("g1", "u1", "Asia/Shanghai")
        await storage.set_alias("viewer1", "u1", "老王")
        handler = TimeCommandHandler(storage, TimeService(), FakeRenderService())

        event = FakeEvent(
            "/time list",
            group_id="g1",
            sender_id="viewer1",
            group_members={"u1": ("当前群名片", "用户名")},
        )
        result = await _collect(handler.handle(event))

        assert "老王" in result[0]
        assert "当前群名片" not in result[0]

    asyncio.run(_run())
