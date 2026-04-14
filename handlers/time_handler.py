from __future__ import annotations

import inspect
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

    def _sender_group_name(self, event: Any) -> str | None:
        message_obj = getattr(event, "message_obj", None)
        raw_message = getattr(message_obj, "raw_message", None)
        sender = (
            raw_message.get("sender")
            if isinstance(raw_message, dict)
            else getattr(raw_message, "sender", None)
        ) or getattr(message_obj, "sender", None)
        if isinstance(sender, dict):
            if "card" in sender:
                return str(sender.get("card") or "").strip()
            return str(sender.get("nickname") or "").strip()
        if hasattr(sender, "card"):
            return str(getattr(sender, "card", "") or "").strip()
        return str(getattr(sender, "nickname", "") or "").strip() or None

    async def _load_users(
        self,
        event: Any,
        target_uids: list[str] | None = None,
    ) -> tuple[str | None, str, dict[str, dict], dict[str, str]]:
        group_id = event.get_group_id()
        viewer = str(event.get_sender_id())
        if not group_id:
            return None, viewer, {}, {}

        users = await self.storage.list_timezones(
            str(group_id),
            viewer=viewer,
            target_uids=target_uids,
        )
        if not hasattr(event, "get_group"):
            return str(group_id), viewer, users, {}

        try:
            group = event.get_group(group_id)
            if inspect.isawaitable(group):
                group = await group
        except Exception:
            return str(group_id), viewer, users, {}

        wanted = {str(uid) for uid in (target_uids or list(users))}
        names: dict[str, str] = {}
        for member in getattr(group, "members", None) or []:
            uid = str(getattr(member, "user_id", "") or "")
            if not uid or uid not in wanted:
                continue
            if hasattr(member, "card"):
                names[uid] = str(getattr(member, "card", "") or "").strip()
                continue
            name = str(getattr(member, "nickname", "") or "").strip()
            if name:
                names[uid] = name
        sender_uid = str(event.get_sender_id())
        sender_name = self._sender_group_name(event)
        if sender_name is not None and sender_uid in wanted:
            names[sender_uid] = sender_name
        users = {
            uid: ({**info, "name": names[uid]} if uid in names else info)
            for uid, info in users.items()
        }
        return str(group_id), viewer, users, names

    def _info(
        self,
        uid: str,
        aliases: dict[str, str] | None = None,
        names: dict[str, str] | None = None,
        fallback: str | None = None,
    ) -> dict[str, str]:
        info = {"alias": aliases[uid]} if aliases and uid in aliases else {}
        if names and uid in names:
            info["name"] = names[uid]
        elif fallback:
            info["name"] = str(fallback)
        return info

    def _render(self, event: Any, entries: list, header: str, viewer: str):
        return event.chain_result(
            self.render_service.render_entries(
                event,
                entries,
                header,
                display_name_fn=self._display_name,
                viewer=viewer,
            )
        )

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

        action, rest = tokens[0].lower(), tokens[1:]
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
        group_id, viewer, users, _ = await self._load_users(event)
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return
        if not users:
            yield event.plain_result(
                "本群还没有成员登记时区～\n使用 /time set <时区> 登记（如 /time set Asia/Shanghai）"
            )
            return

        entries, _ = self.time_service.build_entries(users)
        if not entries:
            yield event.plain_result("本群登记数据异常，请重新登记")
            return
        yield self._render(event, entries, f"本群 {len(entries)} 位成员当前时间", viewer)

    async def _show_member_times(self, event: Any, target_uids: list[str]):
        group_id, viewer, users, names = await self._load_users(event, target_uids)
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return

        missing = [uid for uid in target_uids if uid not in users]
        present = [uid for uid in target_uids if uid in users]
        if not present:
            yield event.plain_result("被查询的成员尚未登记时区\n可让对方使用 /time set <时区> 登记")
            return

        entries, _ = self.time_service.build_entries(users, present)
        if not entries:
            yield event.plain_result("被查询成员的登记数据异常，请重新登记")
            return

        uid0, info0, _ = entries[0]
        header = f"{self._display_name(uid0, info0, viewer=viewer)} 的当前时间" if len(entries) == 1 else f"{len(entries)} 位成员的当前时间"
        chain = self._render(event, entries, header, viewer)
        if missing:
            import astrbot.api.message_components as Comp

            aliases = await self.storage.list_aliases(viewer, missing)
            miss_names = [
                self._display_name(uid, self._info(uid, aliases, names), viewer=viewer)
                for uid in missing
            ]
            chain.append(Comp.Plain(f"{DIVIDER}\n未登记：{'、'.join(miss_names)}"))
        yield chain

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

        try:
            _, canonical = self.time_service.parse_tz(" ".join(rest))
        except ValueError as e:
            yield event.plain_result(f"错误：{e}")
            return

        uid = str(event.get_sender_id())
        await self.storage.upsert_timezone(str(group_id), uid, canonical)
        _, _, _, names = await self._load_users(event, [uid])
        sender_name = self._sender_group_name(event)
        info = self._info(
            uid,
            aliases=await self.storage.list_aliases(uid, [uid]),
            names={uid: sender_name} if sender_name is not None else names,
            fallback=None if sender_name is not None else event.get_sender_name(),
        )

        msg = f"已登记 {self._display_name(uid, info, viewer=uid)} 的时区为 {canonical}"
        if canonical.upper().startswith("UTC"):
            msg += "\n提示：固定 UTC 偏移不会随夏令时自动切换，若需要自动切换请使用地区时区（如 America/New_York）"
        yield event.plain_result(msg)

    async def _unset_tz(self, event: Any):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return
        if not await self.storage.delete_timezone(str(group_id), str(event.get_sender_id())):
            yield event.plain_result("你还没有登记时区")
            return
        yield event.plain_result("已移除你的时区登记")

    async def _list_tz(self, event: Any):
        group_id, viewer, users, _ = await self._load_users(event)
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return
        if not users:
            yield event.plain_result("本群暂无登记")
            return

        lines = [f"本群已登记 {len(users)} 人", DIVIDER]
        for uid, info in users.items():
            lines.extend([f"· {self._display_name(uid, info, viewer=viewer)}", f"  {info.get('tz')}  ·  {uid}"])
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
        if sub in ADMIN_REMOVE_ALIASES and len(rest) >= 2:
            target = rest[1]
            _, viewer, users, _ = await self._load_users(event, [target])
            if target not in users:
                yield event.plain_result(f"{target} 未登记")
                return
            await self.storage.delete_timezone(str(group_id), target)
            yield event.plain_result(
                f"已移除 {self._display_name(target, users[target], viewer=viewer)}（{target}）的时区登记"
            )
        elif sub == "clear":
            yield event.plain_result(
                "已清空本群所有时区登记"
                if await self.storage.clear_group_timezones(str(group_id))
                else "本群暂无登记"
            )
        else:
            yield event.plain_result("未知的管理员子命令，使用 /time admin 查看用法")
