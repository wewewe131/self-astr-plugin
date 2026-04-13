from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable

try:
    from ..core.constants import DIVIDER, QQ_AVATAR_URL, QQ_PLATFORMS
    from ..core.types import Entry
except ImportError:  # pragma: no cover - local direct-import fallback
    from core.constants import DIVIDER, QQ_AVATAR_URL, QQ_PLATFORMS
    from core.types import Entry


class RenderService:
    def render_entries(
        self,
        event: Any,
        entries: list[Entry],
        header: str,
        display_name_fn: Callable[[str, dict | None, str | None], str],
        viewer: str | None = None,
    ) -> list[Any]:
        import astrbot.api.message_components as Comp

        platform = event.get_platform_name()
        show_avatar = platform in QQ_PLATFORMS

        chain: list[Any] = [Comp.Plain(f"{header}\n{DIVIDER}\n")]
        for idx, (uid, info, local) in enumerate(entries):
            if idx > 0:
                chain.append(Comp.Plain(f"{DIVIDER}\n"))
            avatar_shown = show_avatar and uid.isdigit()
            if avatar_shown:
                chain.append(Comp.Image.fromURL(QQ_AVATAR_URL.format(uid=uid)))
            name = display_name_fn(uid, info, viewer)
            tz_label = str(info.get("tz", "?"))
            if tz_label.upper().startswith("UTC"):
                tz_display = tz_label
            else:
                offset_raw = local.strftime("%z")
                if offset_raw:
                    tz_display = f"{tz_label} (UTC{offset_raw[:3]}:{offset_raw[3:]})"
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
