from __future__ import annotations

from datetime import datetime
from typing import TypedDict


class UserInfo(TypedDict, total=False):
    tz: str
    name: str
    alias: str


TimezoneData = dict[str, dict[str, UserInfo]]
AliasData = dict[str, dict[str, str]]

Entry = tuple[str, UserInfo, datetime]
