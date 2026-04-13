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
QQ_AVATAR_URL = "https://q1.qlogo.cn/g?b=qq&nk={uid}&s=100"
QQ_PLATFORMS = {"aiocqhttp", "qq_official"}
OFFSET_RE = re.compile(
    r"^(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE
)

HELP_TEXT = (
    "时间插件用法：\n"
    "  /time                查看本群所有已登记成员的当前时间\n"
    "  /time set <时区>     登记/修改自己的时区\n"
    "                       例：/time set Asia/Shanghai 或 /time set +8\n"
    "  /time unset          移除自己的时区登记\n"
    "  /time list           列出本群所有登记\n"
    "  /time help           显示本帮助\n"
    "管理员：\n"
    "  /time admin remove <user_id>   移除指定成员的登记\n"
    "  /time admin clear              清空本群所有登记"
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

    async def initialize(self):
        """从框架 KV 存储加载数据到内存缓存。"""
        try:
            loaded = await self.get_kv_data(KV_KEY, {})
            self._data = loaded if isinstance(loaded, dict) else {}
        except Exception as e:
            logger.error(f"[time] failed to load kv data: {e}")
            self._data = {}

    async def _save(self) -> None:
        async with self._lock:
            try:
                await self.put_kv_data(KV_KEY, self._data)
            except Exception as e:
                logger.error(f"[time] failed to save kv data: {e}")

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
    def _strip_cmd_prefix(raw: str) -> list[str]:
        tokens = (raw or "").strip().split()
        for i, tok in enumerate(tokens):
            if tok.lstrip("/!").lower() == "time":
                return tokens[i + 1 :]
        return tokens

    @filter.command("time", alias={"时间"})
    async def time_cmd(self, event: AstrMessageEvent):
        """查看本群成员的时区时间；/time help 查看完整用法"""
        tokens = self._strip_cmd_prefix(event.message_str or "")

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

        now_utc = datetime.now(dt_timezone.utc)
        entries: list[tuple[str, dict, datetime]] = []
        for uid, info in users.items():
            try:
                tz, _ = self._parse_tz(info.get("tz", ""))
                local = now_utc.astimezone(tz)
                entries.append((uid, info, local))
            except Exception as e:
                logger.warning(f"[time] bad tz for {uid}: {e}")

        if not entries:
            yield event.plain_result("本群登记数据异常，请重新登记")
            return

        entries.sort(key=lambda x: x[2].utcoffset() or timedelta(0))

        platform = event.get_platform_name()
        show_avatar = platform in QQ_PLATFORMS

        chain: list = [
            Comp.Plain(f"本群共 {len(entries)} 位成员的当前时间：\n\n")
        ]
        for uid, info, local in entries:
            if show_avatar and uid.isdigit():
                chain.append(Comp.Image.fromURL(QQ_AVATAR_URL.format(uid=uid)))
            name = info.get("name") or uid
            tz_label = info.get("tz", "?")
            chain.append(
                Comp.Plain(
                    f" {name} [{tz_label}]\n"
                    f"  {local.strftime('%Y-%m-%d %H:%M:%S %Z').rstrip()}\n\n"
                )
            )

        yield event.chain_result(chain)

    async def _set_tz(self, event: AstrMessageEvent, rest: list[str]):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群组中使用")
            return
        if not rest:
            yield event.plain_result(
                "用法：/time set <时区>\n例：/time set Asia/Shanghai 或 /time set +8"
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
        yield event.plain_result(f"已登记 {name} 的时区为 {canonical}")

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
        lines = [f"本群已登记 {len(users)} 人："]
        for uid, info in users.items():
            lines.append(f"  - {info.get('name') or uid} [{uid}]: {info.get('tz')}")
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
                "管理员用法：\n"
                "  /time admin remove <user_id>\n"
                "  /time admin clear"
            )
            return

        sub = rest[0].lower()
        gkey = str(group_id)

        if sub in ("remove", "rm", "del", "delete") and len(rest) >= 2:
            target = rest[1]
            if target in self._data.get(gkey, {}):
                del self._data[gkey][target]
                if not self._data[gkey]:
                    del self._data[gkey]
                await self._save()
                yield event.plain_result(f"已移除 {target} 的时区登记")
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
