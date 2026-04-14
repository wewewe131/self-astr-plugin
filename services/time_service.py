from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from ..core.constants import OFFSET_RE
    from ..core.types import Entry, UserInfo
except ImportError:  # pragma: no cover - local direct-import fallback
    from core.constants import OFFSET_RE
    from core.types import Entry, UserInfo

try:
    from astrbot.api import logger
except Exception:  # pragma: no cover - for local tests without astrbot
    logger = logging.getLogger(__name__)


class TimeService:
    def parse_tz(self, text: str):
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

    def display_name(
        self,
        uid: str,
        info: UserInfo | None = None,
    ) -> str:
        if info and info.get("alias"):
            return str(info["alias"])
        if info and info.get("name"):
            return str(info["name"])
        return str(uid)

    def build_entries(
        self,
        users: dict[str, UserInfo],
        uids: list[str] | None = None,
    ) -> tuple[list[Entry], list[str]]:
        now_utc = datetime.now(dt_timezone.utc)
        entries: list[Entry] = []
        bad: list[str] = []
        iter_uids = uids if uids is not None else list(users.keys())
        for uid in iter_uids:
            info = users.get(uid)
            if not info:
                continue
            try:
                tz, _ = self.parse_tz(info.get("tz", ""))
                local = now_utc.astimezone(tz)
                entries.append((uid, info, local))
            except Exception as e:
                logger.warning(f"[time] bad tz for {uid}: {e}")
                bad.append(uid)
        entries.sort(key=lambda x: x[2].utcoffset() or timedelta(0))
        return entries, bad
