from __future__ import annotations

from typing import Any


def strip_cmd_prefix(raw: str, names: tuple[str, ...] = ("time",)) -> list[str]:
    tokens = (raw or "").strip().split()
    for i, tok in enumerate(tokens):
        if tok.lstrip("/!").lower() in names:
            return tokens[i + 1 :]
    return tokens


def extract_at_targets(event: Any) -> list[str]:
    """提取被 @ 的成员 ID（排除机器人自己与 @all）。"""
    self_id = ""
    try:
        self_id = str(getattr(event.message_obj, "self_id", "") or "")
    except Exception:
        pass

    try:
        chain = event.get_messages() or []
    except Exception:
        chain = []

    targets: list[str] = []
    for comp in chain:
        is_at = comp.__class__.__name__ == "At" or hasattr(comp, "qq")
        if not is_at:
            continue
        qq = str(getattr(comp, "qq", "") or "").strip()
        if not qq or qq.lower() == "all":
            continue
        if self_id and qq == self_id:
            continue
        if qq not in targets:
            targets.append(qq)
    return targets


def drop_at_tokens(tokens: list[str]) -> list[str]:
    return [t for t in tokens if not t.startswith("@")]


def extract_text_without_mentions(event: Any) -> str:
    """从消息链中提取非 @ 的纯文本内容。"""
    try:
        chain = event.get_messages() or []
    except Exception:
        return ""

    parts: list[str] = []
    for comp in chain:
        is_at = comp.__class__.__name__ == "At" or hasattr(comp, "qq")
        if is_at:
            continue
        text = getattr(comp, "text", None)
        if text is None:
            continue
        parts.append(str(text))
    return "".join(parts).strip()
