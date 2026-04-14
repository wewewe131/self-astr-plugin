import asyncio

from handlers.time_handler import TimeCommandHandler
from services.storage_service import StorageService
from services.time_service import TimeService


class FakeRenderService:
    def render_entries(self, event, entries, header, display_name_fn, viewer=None):
        return [f"{header}:{len(entries)}"]


class MsgObj:
    def __init__(self, self_id=""):
        self.self_id = self_id


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
    ):
        self.message_str = message_str
        self._group_id = group_id
        self._sender_id = sender_id
        self._sender_name = sender_name
        self._admin = admin
        self._platform = platform
        self._messages = messages or []
        self.message_obj = MsgObj()

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

        set_evt = FakeEvent("/time set +8", group_id="g1", sender_id="u1", sender_name="U1")
        set_result = await _collect(handler.handle(set_evt))
        assert "已登记 U1 的时区为 UTC+08:00" in set_result[0]

        list_evt = FakeEvent("/time list", group_id="g1", sender_id="u1")
        list_result = await _collect(handler.handle(list_evt))
        assert "本群已登记 1 人" in list_result[0]

    asyncio.run(_run())
