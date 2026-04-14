from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

try:
    from .handlers.alias_handler import AliasCommandHandler
    from .handlers.help_handler import HelpCommandHandler
    from .handlers.time_handler import TimeCommandHandler
    from .services.render_service import RenderService
    from .services.storage_service import StorageService
    from .services.time_service import TimeService
except ImportError:  # pragma: no cover - local direct-import fallback
    import sys
    from pathlib import Path

    plugin_root = str(Path(__file__).resolve().parent)
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)

    from handlers.alias_handler import AliasCommandHandler
    from handlers.help_handler import HelpCommandHandler
    from handlers.time_handler import TimeCommandHandler
    from services.render_service import RenderService
    from services.storage_service import StorageService
    from services.time_service import TimeService


@register(
    "astrbot_plugin_time",
    "wewewe131",
    "按群组维护成员时区，/time 输出所有登记成员当前时间（含头像缩略图）",
    "1.0.0",
)
class TimePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

        self.storage = StorageService()
        self.time_service = TimeService()
        self.render_service = RenderService()

        self.time_handler = TimeCommandHandler(
            storage=self.storage,
            time_service=self.time_service,
            render_service=self.render_service,
        )
        self.alias_handler = AliasCommandHandler(storage=self.storage)
        self.help_handler = HelpCommandHandler()

    async def initialize(self):
        await self.storage.initialize()

    @filter.command("time", alias={"时间"})
    async def time_cmd(self, event: AstrMessageEvent):
        """查看本群成员的时区时间；/time help 查看完整用法"""
        async for r in self.time_handler.handle(event):
            yield r

    @filter.command("alias", alias={"别名"})
    async def alias_cmd(self, event: AstrMessageEvent):
        """为群友设置仅自己可见的名片；/alias help 查看完整用法"""
        async for r in self.alias_handler.handle(event):
            yield r

    @filter.command("help", alias={"帮助"})
    async def help_cmd(self, event: AstrMessageEvent):
        """展示时间插件所有命令的总览"""
        async for r in self.help_handler.handle(event):
            yield r

    async def terminate(self):
        """插件停用时触发。数据已在每次变更时即时持久化，这里无需额外处理。"""
