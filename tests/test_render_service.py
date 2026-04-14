from core.constants import QQ_AVATAR_URL
from types import ModuleType, SimpleNamespace
import sys

from services.render_service import RenderService


def test_render_entries_does_not_forward_viewer_to_display_name_fn(monkeypatch):
    comp_mod = ModuleType("astrbot.api.message_components")
    comp_mod.Plain = lambda text: ("Plain", text)
    comp_mod.Image = SimpleNamespace(fromURL=lambda url: ("Image", url))

    api_mod = ModuleType("astrbot.api")
    api_mod.message_components = comp_mod

    astrbot_mod = ModuleType("astrbot")
    astrbot_mod.api = api_mod

    monkeypatch.setitem(sys.modules, "astrbot", astrbot_mod)
    monkeypatch.setitem(sys.modules, "astrbot.api", api_mod)
    monkeypatch.setitem(sys.modules, "astrbot.api.message_components", comp_mod)

    calls: list[tuple[str, dict | None]] = []

    def display_name_fn(uid, info):
        calls.append((uid, info))
        return f"name-{uid}"

    class Event:
        def get_platform_name(self):
            return "aiocqhttp"

    entries = [("123", {"tz": "UTC+08:00"}, SimpleNamespace(strftime=lambda fmt: "2026-04-14 20:39:21", dst=lambda: 0))]
    result = RenderService().render_entries(
        Event(),
        entries,
        "header",
        display_name_fn,
        viewer="viewer1",
    )

    assert calls == [("123", {"tz": "UTC+08:00"})]
    assert result[0] == ("Plain", "header\n──────────────\n")
    assert result[1] == ("Image", QQ_AVATAR_URL.format(uid="123"))
    assert result[2] == ("Plain", " name-123\nUTC+08:00\n2026-04-14 20:39:21\n")
