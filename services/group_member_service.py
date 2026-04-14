from __future__ import annotations

import inspect
from typing import Any


class GroupMemberService:
    def _field(self, value: Any, field: str) -> Any:
        if isinstance(value, dict):
            return value.get(field)
        return getattr(value, field, None)

    def _preferred_name(self, value: Any) -> str | None:
        if isinstance(value, dict):
            if "card" in value:
                card = str(value.get("card") or "").strip()
                if card:
                    return card
            nickname = value.get("nickname")
            name = str(nickname or "").strip()
            return name or None

        if hasattr(value, "card"):
            card = str(getattr(value, "card", "") or "").strip()
            if card:
                return card

        nickname = getattr(value, "nickname", None)
        name = str(nickname or "").strip()
        return name or None

    async def _group_members(self, group: Any) -> list[Any]:
        if isinstance(group, dict):
            members = group.get("members")
            if members is not None:
                return list(members)
            members = group.get("member_list")
            return list(members or [])

        members = getattr(group, "members", None)
        if members is not None:
            return list(members)

        members = getattr(group, "member_list", None)
        if members is not None:
            return list(members)

        get_members = getattr(group, "get_members", None)
        if callable(get_members):
            members = get_members()
            if inspect.isawaitable(members):
                members = await members
            return list(members or [])

        return []

    def _normalize_member(self, member: Any) -> dict[str, str] | None:
        uid = str(self._field(member, "user_id") or "").strip()
        if not uid:
            return None

        normalized = {"user_id": uid}
        name = self._preferred_name(member)
        if name is not None:
            normalized["name"] = name
        return normalized

    async def _raw_aiocqhttp_members(self, event: Any, group_id: str) -> list[Any] | None:
        try:
            platform = str(event.get_platform_name() or "")
        except Exception:
            return None

        if platform != "aiocqhttp":
            return None

        bot = getattr(event, "bot", None)
        call_action = getattr(bot, "call_action", None)
        if not callable(call_action):
            return None

        raw_group_id: str | int = group_id
        if str(group_id).isdigit():
            raw_group_id = int(group_id)

        try:
            members = await call_action(
                "get_group_member_list",
                group_id=raw_group_id,
            )
        except Exception:
            return None
        return list(members or [])

    async def members(self, event: Any, group_id: str) -> list[dict[str, str]]:
        members = await self._raw_aiocqhttp_members(event, group_id)
        if members is None:
            if not hasattr(event, "get_group"):
                return []

            try:
                group = event.get_group(group_id)
                if inspect.isawaitable(group):
                    group = await group
            except Exception:
                return []

            members = await self._group_members(group)

        normalized: list[dict[str, str]] = []
        for member in members:
            item = self._normalize_member(member)
            if item is not None:
                normalized.append(item)
        return normalized

    async def member_names(
        self,
        event: Any,
        group_id: str,
        wanted: set[str] | None = None,
    ) -> dict[str, str]:
        names: dict[str, str] = {}
        for member in await self.members(event, group_id):
            uid = member["user_id"]
            if wanted is not None and uid not in wanted:
                continue
            name = member.get("name")
            if name is not None:
                names[uid] = name
        return names

    def sender_name(self, event: Any) -> str | None:
        message_obj = getattr(event, "message_obj", None)
        raw_message = getattr(message_obj, "raw_message", None)
        sender = (
            raw_message.get("sender")
            if isinstance(raw_message, dict)
            else getattr(raw_message, "sender", None)
        ) or getattr(message_obj, "sender", None)
        return self._preferred_name(sender)
