from __future__ import annotations

from typing import Any

try:
    from ..core.constants import MODULE_HELP_TEXT
except ImportError:  # pragma: no cover - local direct-import fallback
    from core.constants import MODULE_HELP_TEXT


class HelpCommandHandler:
    async def handle(self, event: Any):
        yield event.plain_result(MODULE_HELP_TEXT)
