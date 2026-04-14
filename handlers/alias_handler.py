from __future__ import annotations

from typing import Any

try:
    from ..core.constants import (
        ALIAS_CLEAR_ALIASES,
        ALIAS_HELP_TEXT,
        ALIAS_MAX_LEN,
        ALIAS_UNSET_ALIASES,
        DIVIDER,
        HELP_ALIASES,
    )
    from ..core.parsers import (
        drop_at_tokens,
        extract_at_targets,
        extract_text_without_mentions,
        strip_cmd_prefix,
    )
    from ..services.storage_service import StorageService
except ImportError:  # pragma: no cover - local direct-import fallback
    from core.constants import (
        ALIAS_CLEAR_ALIASES,
        ALIAS_HELP_TEXT,
        ALIAS_MAX_LEN,
        ALIAS_UNSET_ALIASES,
        DIVIDER,
        HELP_ALIASES,
    )
    from core.parsers import (
        drop_at_tokens,
        extract_at_targets,
        extract_text_without_mentions,
        strip_cmd_prefix,
    )
    from services.storage_service import StorageService


class AliasCommandHandler:
    def __init__(self, storage: StorageService):
        self.storage = storage

    async def handle(self, event: Any):
        tokens = strip_cmd_prefix(event.message_str or "", names=("alias", "别名"))
        at_targets = extract_at_targets(event)
        owner = str(event.get_sender_id())

        clean = drop_at_tokens(tokens)
        text_without_mentions = extract_text_without_mentions(event)
        text_tokens = strip_cmd_prefix(text_without_mentions, names=("alias", "别名"))

        if not at_targets:
            if not clean:
                owned = await self.storage.list_aliases(owner)
                if not owned:
                    yield event.plain_result(
                        "你还没有为任何人设置名片\n"
                        "设置：/alias @成员 <别名>"
                    )
                    return
                lines = [f"你设置的名片（{len(owned)}）", DIVIDER]
                for tgt, alias in owned.items():
                    lines.append(f"· {alias}  ←  {tgt}")
                yield event.plain_result("\n".join(lines))
                return

            first = clean[0].lower()
            if first in HELP_ALIASES:
                yield event.plain_result(ALIAS_HELP_TEXT)
                return
            if first in ALIAS_CLEAR_ALIASES:
                removed = await self.storage.clear_aliases(owner)
                if removed:
                    yield event.plain_result("已清除你设置的全部名片")
                else:
                    yield event.plain_result("你还没有设置任何名片")
                return

            yield event.plain_result(
                "请通过 @ 指定目标成员\n"
                "例：/alias @成员 老王\n\n" + ALIAS_HELP_TEXT
            )
            return

        action_tokens = text_tokens or clean

        if action_tokens and action_tokens[0].lower() in ALIAS_UNSET_ALIASES:
            removed_map = await self.storage.delete_aliases(owner, at_targets)
            removed, missing = [], []
            for tgt in at_targets:
                if tgt in removed_map:
                    removed.append(f"{removed_map[tgt]}（{tgt}）")
                else:
                    missing.append(tgt)
            parts = []
            if removed:
                parts.append("已移除名片：" + "、".join(removed))
            if missing:
                parts.append("尚未设置：" + "、".join(missing))
            yield event.plain_result("\n".join(parts) or "无变更")
            return

        if not action_tokens:
            owned = await self.storage.list_aliases(owner, at_targets)
            lines = []
            for tgt in at_targets:
                if tgt in owned:
                    lines.append(f"· {tgt} → {owned[tgt]}")
                else:
                    lines.append(f"· {tgt} 尚未设置名片")
            yield event.plain_result("\n".join(lines))
            return

        if len(at_targets) > 1:
            yield event.plain_result("一次只能为一位成员设置名片")
            return

        new_alias = " ".join(action_tokens).strip()
        if not new_alias:
            yield event.plain_result("别名不能为空")
            return
        if len(new_alias) > ALIAS_MAX_LEN:
            yield event.plain_result(f"别名过长（最多 {ALIAS_MAX_LEN} 字符）")
            return

        target = at_targets[0]
        await self.storage.set_alias(owner, target, new_alias)
        yield event.plain_result(f"已将 {target} 的名片设置为：{new_alias}\n（仅你自己可见）")
