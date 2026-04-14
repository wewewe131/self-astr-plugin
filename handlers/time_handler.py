from __future__ import annotations

from typing import Any

try:
    from ..core.constants import (
        ADMIN_REMOVE_ALIASES,
        DIVIDER,
        HELP_ALIASES,
        HELP_TEXT,
        TIME_LIST_ALIASES,
        TIME_SET_ALIASES,
        TIME_UNSET_ALIASES,
    )
    from ..core.parsers import extract_at_targets, strip_cmd_prefix
    from ..services.render_service import RenderService
    from ..services.storage_service import StorageService
    from ..services.time_service import TimeService
except ImportError:  # pragma: no cover - local direct-import fallback
    from core.constants import (
        ADMIN_REMOVE_ALIASES,
        DIVIDER,
        HELP_ALIASES,
        HELP_TEXT,
        TIME_LIST_ALIASES,
        TIME_SET_ALIASES,
        TIME_UNSET_ALIASES,
    )
    from core.parsers import extract_at_targets, strip_cmd_prefix
    from services.render_service import RenderService
    from services.storage_service import StorageService
    from services.time_service import TimeService


class TimeCommandHandler:
    def __init__(
        self,
        storage: StorageService,
        time_service: TimeService,
        render_service: RenderService,
    ):
        self.storage = storage
        self.time_service = time_service
        self.render_service = render_service

    def _display_name(self, uid: str, info: dict | None = None, viewer: str | None = None) -> str:
        return self.time_service.display_name(uid, info=info)

    async def handle(self, event: Any):
        tokens = strip_cmd_prefix(event.message_str or "")
        at_targets = extract_at_targets(event)

        if at_targets:
            async for r in self._show_member_times(event, at_targets):
                yield r
            return

        if not tokens:
            async for r in self._show_group_times(event):
                yield r
            return

        action = tokens[0].lower()
        rest = tokens[1:]

        if action in TIME_SET_ALIASES:
            async for r in self._set_tz(event, rest):
                yield r
        elif action in TIME_UNSET_ALIASES:
            async for r in self._unset_tz(event):
                yield r
        elif action in TIME_LIST_ALIASES:
            async for r in self._list_tz(event):
                yield r
        elif action in HELP_ALIASES:
            yield event.plain_result(HELP_TEXT)
        elif action == "admin":
            async for r in self._admin(event, rest):
                yield r
        else:
            yield event.plain_result(f"未知子命令：{action}\n\n{HELP_TEXT}")

    async def _show_group_times(self, event: Any):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return

        viewer = str(event.get_sender_id())
        users = await self.storage.list_timezones(str(group_id), viewer=viewer)
        if not users:
            yield event.plain_result(
                "本群还没有成员登记时区～\n使用 /time set <时区> 登记（如 /time set Asia/Shanghai）"
            )
            return

        entries, _ = self.time_service.build_entries(users)
        if not entries:
            yield event.plain_result("本群登记数据异常，请重新登记")
            return

        chain = self.render_service.render_entries(
            event,
            entries,
            f"本群 {len(entries)} 位成员当前时间",
            display_name_fn=self._display_name,
            viewer=viewer,
        )
        yield event.chain_result(chain)

    async def _show_member_times(self, event: Any, target_uids: list[str]):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return

        viewer = str(event.get_sender_id())
        users = await self.storage.list_timezones(
            str(group_id),
            viewer=viewer,
            target_uids=target_uids,
        )
        missing = [uid for uid in target_uids if uid not in users]
        present = [uid for uid in target_uids if uid in users]

        if not present:
            yield event.plain_result(
                "被查询的成员尚未登记时区\n可让对方使用 /time set <时区> 登记"
            )
            return

        entries, _ = self.time_service.build_entries(users, present)
        if not entries:
            yield event.plain_result("被查询成员的登记数据异常，请重新登记")
            return

        if len(entries) == 1:
            uid0, info0, _ = entries[0]
            header = f"{self._display_name(uid0, info0, viewer=viewer)} 的当前时间"
        else:
            header = f"{len(entries)} 位成员的当前时间"
        chain = self.render_service.render_entries(
            event,
            entries,
            header,
            display_name_fn=self._display_name,
            viewer=viewer,
        )
        if missing:
            miss_names = "、".join(missing)
            import astrbot.api.message_components as Comp

            chain.append(Comp.Plain(f"{DIVIDER}\n未登记：{miss_names}"))
        yield event.chain_result(chain)

    async def _set_tz(self, event: Any, rest: list[str]):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return
        if not rest:
            yield event.plain_result(
                "用法：/time set <时区>\n"
                "例：/time set Asia/Shanghai 或 /time set +8\n"
                "建议：使用地区时区可自动处理夏令时（如 America/New_York）"
            )
            return

        tz_text = " ".join(rest)
        try:
            _, canonical = self.time_service.parse_tz(tz_text)
        except ValueError as e:
            yield event.plain_result(f"错误：{e}")
            return

        uid = str(event.get_sender_id())
        name = event.get_sender_name() or uid
        gkey = str(group_id)
        await self.storage.upsert_timezone(gkey, uid, canonical, name)

        display_name = self._display_name(uid, {"name": name}, viewer=uid)
        msg = f"已登记 {display_name} 的时区为 {canonical}"
        if canonical.upper().startswith("UTC"):
            msg += "\n提示：固定 UTC 偏移不会随夏令时自动切换，若需要自动切换请使用地区时区（如 America/New_York）"
        yield event.plain_result(msg)

    async def _unset_tz(self, event: Any):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return
        uid = str(event.get_sender_id())
        gkey = str(group_id)
        removed = await self.storage.delete_timezone(gkey, uid)
        if not removed:
            yield event.plain_result("你还没有登记时区")
            return
        yield event.plain_result("已移除你的时区登记")

    async def _list_tz(self, event: Any):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return
        viewer = str(event.get_sender_id())
        users = await self.storage.list_timezones(str(group_id), viewer=viewer)
        if not users:
            yield event.plain_result("本群暂无登记")
            return
        lines = [f"本群已登记 {len(users)} 人", DIVIDER]
        for uid, info in users.items():
            lines.append(f"· {self._display_name(uid, info, viewer=viewer)}")
            lines.append(f"  {info.get('tz')}  ·  {uid}")
        yield event.plain_result("\n".join(lines))

    async def _admin(self, event: Any, rest: list[str]):
        if not event.is_admin():
            yield event.plain_result("该操作仅限管理员")
            return
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return
        if not rest:
            yield event.plain_result(
                "管理员用法\n"
                f"{DIVIDER}\n"
                "/time admin remove <user_id>\n"
                "  移除指定成员的登记\n"
                "/time admin clear\n"
                "  清空本群所有登记"
            )
            return

        sub = rest[0].lower()
        gkey = str(group_id)

        if sub in ADMIN_REMOVE_ALIASES and len(rest) >= 2:
            target = rest[1]
            target_info = await self.storage.get_timezone(
                gkey,
                target,
                viewer=str(event.get_sender_id()),
            )
            if target_info:
                target_name = self._display_name(
                    target,
                    target_info,
                    viewer=str(event.get_sender_id()),
                )
                await self.storage.delete_timezone(gkey, target)
                yield event.plain_result(f"已移除 {target_name}（{target}）的时区登记")
            else:
                yield event.plain_result(f"{target} 未登记")
        elif sub == "clear":
            removed = await self.storage.clear_group_timezones(gkey)
            if removed:
                yield event.plain_result("已清空本群所有时区登记")
            else:
                yield event.plain_result("本群暂无登记")
        else:
            yield event.plain_result("未知的管理员子命令，使用 /time admin 查看用法")
