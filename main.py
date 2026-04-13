import asyncio
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


KV_KEY = "timezones"
ALIAS_KV_KEY = "aliases"
ALIAS_MAX_LEN = 24
QQ_AVATAR_URL = "https://q1.qlogo.cn/g?b=qq&nk={uid}&s=100"
QQ_PLATFORMS = {"aiocqhttp", "qq_official"}
OFFSET_RE = re.compile(
    r"^(?:UTC|GMT)?\s*([+-])?\s*(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE
)
DIVIDER = "─" * 14

HELP_TEXT = (
    "时间插件用法\n"
    f"{DIVIDER}\n"
    "/time\n"
    "  查看本群所有登记成员的当前时间\n"
    "/time @成员 [@成员...]\n"
    "  仅查看指定成员的当前时间\n"
    "/time set <时区>\n"
    "  登记/修改自己的时区\n"
    "  例：/time set Asia/Shanghai\n"
    "  例：/time set +8\n"
    "  建议使用地区时区以自动处理夏令时（如 /time set America/New_York）\n"
    "/time unset\n"
    "  移除自己的时区登记\n"
    "/time list\n"
    "  列出本群所有登记\n"
    "/time help\n"
    "  显示本帮助\n"
    "/alias <别名>\n"
    "  设置全局显示别名\n"
    f"{DIVIDER}\n"
    "管理员命令\n"
    "/time admin remove <user_id>\n"
    "  移除指定成员的登记\n"
    "/time admin clear\n"
    "  清空本群所有登记"
)

ALIAS_HELP_TEXT = (
    "名片用法\n"
    f"{DIVIDER}\n"
    "/alias\n"
    "  查看当前名片\n"
    "/alias <别名>\n"
    "  设置/修改名片\n"
    "/alias unset\n"
    "  清除名片\n"
    f"（别名最长 {ALIAS_MAX_LEN} 字符，将覆盖 /time 列表中的显示名）"
)

MODULE_HELP_TEXT = (
    "时间插件命令总览\n"
    f"{DIVIDER}\n"
    "【查看时间】\n"
    "/time\n"
    "  查看本群登记成员的当前时间\n"
    "/time @成员 [@成员...]\n"
    "  仅查看指定成员的当前时间\n"
    "/time list\n"
    "  列出本群所有登记\n"
    f"{DIVIDER}\n"
    "【时区登记】\n"
    "/time set <时区>\n"
    "  登记/修改自己的时区\n"
    "  例：/time set Asia/Shanghai\n"
    "  例：/time set +8\n"
    "  建议使用地区时区以自动处理夏令时（如 America/New_York）\n"
    "/time unset\n"
    "  移除自己的时区登记\n"
    f"{DIVIDER}\n"
    "【名片】\n"
    "/alias\n"
    "  查看当前别名\n"
    "/alias <别名>\n"
    f"  设置/修改别名（≤ {ALIAS_MAX_LEN} 字符）\n"
    "/alias unset\n"
    "  清除别名\n"
    f"{DIVIDER}\n"
    "【帮助】\n"
    "/help\n"
    "  显示本总览\n"
    "/time help\n"
    "  /time 详细帮助\n"
    "/alias help\n"
    "  /alias 详细帮助\n"
    f"{DIVIDER}\n"
    "【管理员】\n"
    "/time admin remove <user_id>\n"
    "  移除指定成员的登记\n"
    "/time admin clear\n"
    "  清空本群所有登记"
)


@register(
    "astrbot_plugin_time",
    "wewewe131",
    "按群组维护成员时区，/time 输出所有登记成员当前时间（含头像缩略图）",
    "1.0.0",
)
class TimePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._lock = asyncio.Lock()
        self._data: dict[str, dict[str, dict[str, Any]]] = {}
        self._aliases: dict[str, str] = {}

    async def initialize(self):
        """从框架 KV 存储加载数据到内存缓存。"""
        try:
            loaded = await self.get_kv_data(KV_KEY, {})
            self._data = loaded if isinstance(loaded, dict) else {}
        except Exception as e:
            logger.error(f"[time] failed to load kv data: {e}")
            self._data = {}
        try:
            loaded_alias = await self.get_kv_data(ALIAS_KV_KEY, {})
            if isinstance(loaded_alias, dict):
                self._aliases = {str(k): str(v) for k, v in loaded_alias.items()}
            else:
                self._aliases = {}
        except Exception as e:
            logger.error(f"[time] failed to load alias data: {e}")
            self._aliases = {}

    async def _save(self) -> None:
        async with self._lock:
            try:
                await self.put_kv_data(KV_KEY, self._data)
            except Exception as e:
                logger.error(f"[time] failed to save kv data: {e}")

    async def _save_aliases(self) -> None:
        async with self._lock:
            try:
                await self.put_kv_data(ALIAS_KV_KEY, self._aliases)
            except Exception as e:
                logger.error(f"[time] failed to save alias data: {e}")

    def _display_name(self, uid: str, info: dict | None = None) -> str:
        alias = self._aliases.get(str(uid))
        if alias:
            return alias
        if info and info.get("name"):
            return info["name"]
        return str(uid)

    @staticmethod
    def _parse_tz(text: str):
        """解析时区字符串，返回 (tzinfo, 规范化字符串)。无效时抛 ValueError。"""
        text = (text or "").strip()
        if not text:
            raise ValueError("时区不能为空")

        try:
            return ZoneInfo(text), text
        except ZoneInfoNotFoundError:
            pass

        m = OFFSET_RE.match(text)
        if m:
            sign, hh, mm = m.groups()
            hh_i = int(hh)
            mm_i = int(mm or 0)
            if hh_i > 14 or mm_i >= 60:
                raise ValueError(f"无效的 UTC 偏移：{text}")
            total_min = hh_i * 60 + mm_i
            if sign == "-":
                total_min = -total_min
            tz = dt_timezone(timedelta(minutes=total_min))
            canonical = "UTC{sign}{h:02d}:{m:02d}".format(
                sign="+" if total_min >= 0 else "-",
                h=abs(total_min) // 60,
                m=abs(total_min) % 60,
            )
            return tz, canonical

        raise ValueError(f"无法识别的时区：{text}（请使用 Asia/Shanghai 或 +8 之类）")

    @staticmethod
    def _strip_cmd_prefix(raw: str, names: tuple[str, ...] = ("time",)) -> list[str]:
        tokens = (raw or "").strip().split()
        for i, tok in enumerate(tokens):
            if tok.lstrip("/!").lower() in names:
                return tokens[i + 1 :]
        return tokens

    @staticmethod
    def _extract_at_targets(event: AstrMessageEvent) -> list[str]:
        """从消息链中提取所有被 @ 的成员 ID（排除机器人自己与 @全体）。"""
        self_id = ""
        try:
            self_id = str(getattr(event.message_obj, "self_id", "") or "")
        except Exception:
            pass
        targets: list[str] = []
        try:
            chain = event.get_messages() or []
        except Exception:
            chain = []
        for comp in chain:
            if not isinstance(comp, Comp.At):
                continue
            qq = str(getattr(comp, "qq", "") or "").strip()
            if not qq or qq.lower() == "all":
                continue
            if self_id and qq == self_id:
                continue
            if qq not in targets:
                targets.append(qq)
        return targets

    @filter.command("time", alias={"时间"})
    async def time_cmd(self, event: AstrMessageEvent):
        """查看本群成员的时区时间；/time help 查看完整用法"""
        tokens = self._strip_cmd_prefix(event.message_str or "")
        at_targets = self._extract_at_targets(event)

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

        if action in ("set", "reg", "register", "设置", "注册"):
            async for r in self._set_tz(event, rest):
                yield r
        elif action in ("unset", "remove", "del", "delete", "移除", "删除"):
            async for r in self._unset_tz(event):
                yield r
        elif action in ("list", "ls", "列表"):
            async for r in self._list_tz(event):
                yield r
        elif action in ("help", "帮助", "?"):
            yield event.plain_result(HELP_TEXT)
        elif action == "admin":
            async for r in self._admin(event, rest):
                yield r
        else:
            yield event.plain_result(f"未知子命令：{action}\n\n{HELP_TEXT}")

    @filter.command("alias", alias={"别名"})
    async def alias_cmd(self, event: AstrMessageEvent):
        """查看或设置自己的全局显示别名；/alias help 查看完整用法"""
        tokens = self._strip_cmd_prefix(
            event.message_str or "", names=("alias", "别名")
        )
        uid = str(event.get_sender_id())

        if not tokens:
            current = self._aliases.get(uid)
            if current:
                yield event.plain_result(
                    f"你当前的名片：{current}\n"
                    "修改：/alias <新别名>\n"
                    "清除：/alias unset"
                )
            else:
                yield event.plain_result(
                    "你还没有设置名片\n"
                    "设置：/alias <别名>"
                )
            return

        first = tokens[0].lower()
        if first in ("help", "帮助", "?"):
            yield event.plain_result(ALIAS_HELP_TEXT)
            return
        if first in ("unset", "remove", "del", "delete", "clear", "移除", "删除", "清除"):
            if uid in self._aliases:
                del self._aliases[uid]
                await self._save_aliases()
                yield event.plain_result("已清除你的名片")
            else:
                yield event.plain_result("你还没有设置名片")
            return

        new_alias = " ".join(tokens).strip()
        if not new_alias:
            yield event.plain_result("别名不能为空")
            return
        if len(new_alias) > ALIAS_MAX_LEN:
            yield event.plain_result(f"别名过长（最多 {ALIAS_MAX_LEN} 字符）")
            return

        self._aliases[uid] = new_alias
        await self._save_aliases()
        yield event.plain_result(f"已设置你的名片为：{new_alias}")

    @filter.command("help", alias={"帮助"})
    async def help_cmd(self, event: AstrMessageEvent):
        """展示时间插件所有命令的总览"""
        yield event.plain_result(MODULE_HELP_TEXT)

    def _build_entries(
        self, users: dict[str, dict[str, Any]], uids: list[str] | None = None
    ) -> tuple[list[tuple[str, dict, datetime]], list[str]]:
        """构造 (uid, info, local_time) 列表，同时返回无法解析的 uid 列表。"""
        now_utc = datetime.now(dt_timezone.utc)
        entries: list[tuple[str, dict, datetime]] = []
        bad: list[str] = []
        iter_uids = uids if uids is not None else list(users.keys())
        for uid in iter_uids:
            info = users.get(uid)
            if not info:
                continue
            try:
                tz, _ = self._parse_tz(info.get("tz", ""))
                local = now_utc.astimezone(tz)
                entries.append((uid, info, local))
            except Exception as e:
                logger.warning(f"[time] bad tz for {uid}: {e}")
                bad.append(uid)
        entries.sort(key=lambda x: x[2].utcoffset() or timedelta(0))
        return entries, bad

    def _render_entries(
        self,
        event: AstrMessageEvent,
        entries: list[tuple[str, dict, datetime]],
        header: str,
    ) -> list:
        platform = event.get_platform_name()
        show_avatar = platform in QQ_PLATFORMS

        chain: list = [Comp.Plain(f"{header}\n{DIVIDER}\n")]
        for idx, (uid, info, local) in enumerate(entries):
            if idx > 0:
                chain.append(Comp.Plain(f"{DIVIDER}\n"))
            avatar_shown = show_avatar and uid.isdigit()
            if avatar_shown:
                chain.append(Comp.Image.fromURL(QQ_AVATAR_URL.format(uid=uid)))
            name = self._display_name(uid, info)
            tz_label = info.get("tz", "?")
            if tz_label.upper().startswith("UTC"):
                tz_display = tz_label
            else:
                offset_raw = local.strftime("%z")
                if offset_raw:
                    tz_display = (
                        f"{tz_label} (UTC{offset_raw[:3]}:{offset_raw[3:]})"
                    )
                else:
                    tz_display = tz_label
                if (local.dst() or timedelta(0)) > timedelta(0):
                    tz_display += " · 夏令时"
            name_line = f" {name}\n" if avatar_shown else f"{name}\n"
            chain.append(
                Comp.Plain(
                    name_line
                    + f"{tz_display}\n"
                    + f"{local.strftime('%Y-%m-%d  %H:%M:%S')}\n"
                )
            )
        return chain

    async def _show_group_times(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return

        users = self._data.get(str(group_id), {})
        if not users:
            yield event.plain_result(
                "本群还没有成员登记时区～\n使用 /time set <时区> 登记（如 /time set Asia/Shanghai）"
            )
            return

        entries, _ = self._build_entries(users)
        if not entries:
            yield event.plain_result("本群登记数据异常，请重新登记")
            return

        chain = self._render_entries(
            event, entries, f"本群 {len(entries)} 位成员当前时间"
        )
        yield event.chain_result(chain)

    async def _show_member_times(
        self, event: AstrMessageEvent, target_uids: list[str]
    ):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return

        users = self._data.get(str(group_id), {})
        missing = [uid for uid in target_uids if uid not in users]
        present = [uid for uid in target_uids if uid in users]

        if not present:
            yield event.plain_result(
                "被查询的成员尚未登记时区\n可让对方使用 /time set <时区> 登记"
            )
            return

        entries, _ = self._build_entries(users, present)
        if not entries:
            yield event.plain_result("被查询成员的登记数据异常，请重新登记")
            return

        if len(entries) == 1:
            uid0, info0, _ = entries[0]
            header = f"{self._display_name(uid0, info0)} 的当前时间"
        else:
            header = f"{len(entries)} 位成员的当前时间"
        chain = self._render_entries(event, entries, header)
        if missing:
            miss_names = "、".join(missing)
            chain.append(
                Comp.Plain(f"{DIVIDER}\n未登记：{miss_names}")
            )
        yield event.chain_result(chain)

    async def _set_tz(self, event: AstrMessageEvent, rest: list[str]):
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
            _, canonical = self._parse_tz(tz_text)
        except ValueError as e:
            yield event.plain_result(f"错误：{e}")
            return

        uid = str(event.get_sender_id())
        name = event.get_sender_name() or uid
        gkey = str(group_id)
        self._data.setdefault(gkey, {})[uid] = {"tz": canonical, "name": name}
        await self._save()
        display_name = self._display_name(uid, {"name": name})
        msg = f"已登记 {display_name} 的时区为 {canonical}"
        if canonical.upper().startswith("UTC"):
            msg += "\n提示：固定 UTC 偏移不会随夏令时自动切换，若需要自动切换请使用地区时区（如 America/New_York）"
        yield event.plain_result(msg)

    async def _unset_tz(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return
        uid = str(event.get_sender_id())
        gkey = str(group_id)
        if uid not in self._data.get(gkey, {}):
            yield event.plain_result("你还没有登记时区")
            return
        del self._data[gkey][uid]
        if not self._data[gkey]:
            del self._data[gkey]
        await self._save()
        yield event.plain_result("已移除你的时区登记")

    async def _list_tz(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return
        users = self._data.get(str(group_id), {})
        if not users:
            yield event.plain_result("本群暂无登记")
            return
        lines = [f"本群已登记 {len(users)} 人", DIVIDER]
        for uid, info in users.items():
            lines.append(f"· {self._display_name(uid, info)}")
            lines.append(f"  {info.get('tz')}  ·  {uid}")
        yield event.plain_result("\n".join(lines))

    async def _admin(self, event: AstrMessageEvent, rest: list[str]):
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

        if sub in ("remove", "rm", "del", "delete") and len(rest) >= 2:
            target = rest[1]
            if target in self._data.get(gkey, {}):
                target_info = self._data[gkey][target]
                target_name = self._display_name(target, target_info)
                del self._data[gkey][target]
                if not self._data[gkey]:
                    del self._data[gkey]
                await self._save()
                yield event.plain_result(f"已移除 {target_name}（{target}）的时区登记")
            else:
                yield event.plain_result(f"{target} 未登记")
        elif sub == "clear":
            if gkey in self._data:
                del self._data[gkey]
                await self._save()
                yield event.plain_result("已清空本群所有时区登记")
            else:
                yield event.plain_result("本群暂无登记")
        else:
            yield event.plain_result("未知的管理员子命令，使用 /time admin 查看用法")

    async def terminate(self):
        """插件停用时触发。数据已在每次变更时即时持久化，这里无需额外处理。"""
