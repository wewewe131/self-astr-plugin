import asyncio

from handlers.alias_handler import AliasCommandHandler
from services.storage_service import StorageService


class At:
    def __init__(self, qq):
        self.qq = qq


class Plain:
    def __init__(self, text):
        self.text = text


class MsgObj:
    def __init__(self, self_id=""):
        self.self_id = self_id


class FakeEvent:
    def __init__(
        self,
        message_str,
        messages=None,
        sender_id="1000",
        sender_name="tester",
    ):
        self.message_str = message_str
        self._messages = messages or []
        self._sender_id = sender_id
        self._sender_name = sender_name
        self.message_obj = MsgObj()

    def get_messages(self):
        return self._messages

    def get_sender_id(self):
        return self._sender_id

    def get_sender_name(self):
        return self._sender_name

    def plain_result(self, text):
        return text


async def _collect(async_gen):
    return [item async for item in async_gen]


def test_alias_set_and_view(tmp_path):
    async def _run():
        storage = StorageService(sqlite_db_path=tmp_path / "data_v4.db")
        await storage.initialize()
        handler = AliasCommandHandler(storage)

        evt_set = FakeEvent("/alias @u2 老王", messages=[At("u2")])
        set_result = await _collect(handler.handle(evt_set))
        assert "已将 u2 的名片设置为：老王" in set_result[0]

        evt_view = FakeEvent("/alias @u2", messages=[At("u2")])
        view_result = await _collect(handler.handle(evt_view))
        assert "u2 → 老王" in view_result[0]

    asyncio.run(_run())


def test_alias_reject_multi_target_set(tmp_path):
    async def _run():
        storage = StorageService(sqlite_db_path=tmp_path / "data_v4.db")
        await storage.initialize()
        handler = AliasCommandHandler(storage)

        evt = FakeEvent("/alias @u2 @u3 张三", messages=[At("u2"), At("u3")])
        result = await _collect(handler.handle(evt))
        assert result == ["一次只能为一位成员设置名片"]

    asyncio.run(_run())


def test_alias_clear_without_data(tmp_path):
    async def _run():
        storage = StorageService(sqlite_db_path=tmp_path / "data_v4.db")
        await storage.initialize()
        handler = AliasCommandHandler(storage)

        evt = FakeEvent("/alias clear")
        result = await _collect(handler.handle(evt))
        assert result == ["你还没有设置任何名片"]

    asyncio.run(_run())


def test_alias_set_uses_message_chain_text_after_at(tmp_path):
    async def _run():
        storage = StorageService(sqlite_db_path=tmp_path / "data_v4.db")
        await storage.initialize()
        handler = AliasCommandHandler(storage)

        evt = FakeEvent(
            '/alias @def f(): print("反重力裙"); f(); f()  乌啪叽',
            messages=[At("u2"), Plain(" 乌啪叽")],
        )
        result = await _collect(handler.handle(evt))
        assert "已将 u2 的名片设置为：乌啪叽" in result[0]

    asyncio.run(_run())


def test_alias_set_keeps_command_and_alias_separated_across_at(tmp_path):
    async def _run():
        storage = StorageService(sqlite_db_path=tmp_path / "data_v4.db")
        await storage.initialize()
        handler = AliasCommandHandler(storage)

        evt = FakeEvent(
            '/alias @def f(): print("反重力裙"); f(); f()  1',
            messages=[Plain("/alias"), At("u2"), Plain("  1")],
        )
        result = await _collect(handler.handle(evt))
        assert "已将 u2 的名片设置为：1" in result[0]

    asyncio.run(_run())
