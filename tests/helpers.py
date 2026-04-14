from types import SimpleNamespace


class At:
    def __init__(self, qq):
        self.qq = qq


class Plain:
    def __init__(self, text):
        self.text = text


class MsgObj:
    def __init__(self, self_id="", sender=None):
        self.self_id = self_id
        self.raw_message = {
            "self_id": self_id,
            "sender": sender or {},
        }


class FakeBot:
    def __init__(self, members=None):
        self._members = members or []

    async def call_action(self, action, **kwargs):
        if action == "get_group_member_list":
            return self._members
        raise AssertionError(f"unexpected action: {action}")


class FakeRenderService:
    def render_entries(self, event, entries, header, display_name_fn, viewer=None):
        return [f"{header}:{len(entries)}"]


class FakeEvent:
    def __init__(
        self,
        message_str,
        group_id=None,
        sender_id="1000",
        sender_name="tester",
        admin=False,
        platform="aiocqhttp",
        messages=None,
        group_members=None,
        sender_card=None,
        group_obj=None,
        bot=None,
    ):
        self.message_str = message_str
        self._group_id = group_id
        self._sender_id = sender_id
        self._sender_name = sender_name
        self._admin = admin
        self._platform = platform
        self._messages = messages or []
        self._group_members = group_members or {}
        self._group_obj = group_obj
        self.bot = bot
        self.message_obj = MsgObj(
            sender={
                "card": sender_card or "",
                "nickname": sender_name,
            }
        )

    def get_group_id(self):
        return self._group_id

    def get_sender_id(self):
        return self._sender_id

    def get_sender_name(self):
        return self._sender_name

    def get_platform_name(self):
        return self._platform

    def get_messages(self):
        return self._messages

    def is_admin(self):
        return self._admin

    async def get_group(self, group_id=None, **kwargs):
        if self._group_obj is not None:
            return self._group_obj
        members = []
        for uid, member in self._group_members.items():
            if isinstance(member, dict):
                members.append({"user_id": uid, **member})
                continue
            members.append(
                SimpleNamespace(
                    user_id=uid,
                    card=member[0] if isinstance(member, tuple) else member,
                    nickname=member[1] if isinstance(member, tuple) else member,
                )
            )
        return SimpleNamespace(members=members)

    def plain_result(self, text):
        return text

    def chain_result(self, chain):
        return chain


async def collect(async_gen):
    return [item async for item in async_gen]
