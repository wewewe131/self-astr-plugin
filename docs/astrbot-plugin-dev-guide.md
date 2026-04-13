# AstrBot 插件开发文档总结

> 来源：https://docs.astrbot.app/dev/star/plugin-new.html 及其子章节
> 抓取时间：2026-04-14

---

## 1. 插件基础结构

### 1.1 目录布局

```
AstrBot/
└── data/plugins/
    └── <plugin_name>/
        ├── main.py              # 入口文件（必须）
        ├── metadata.yaml        # 元数据（必须）
        ├── _conf_schema.json    # 配置声明（可选）
        ├── requirements.txt     # 第三方依赖（可选）
        └── logo.png             # 插件图标 256×256（可选）
```

- 插件目录 / 仓库命名规范：`astrbot_plugin_xxx`，全小写、无空格。
- 推荐基于官方模板仓库 `Soulter/helloworld` 创建。

### 1.2 metadata.yaml 示例

```yaml
display_name: My Plugin
support_platforms:
  - telegram
  - discord
astrbot_version: ">=4.16,<5"   # PEP 440
```

支持的平台适配器取值：`aiocqhttp`、`qq_official`、`telegram`、`wecom`、`lark`、`dingtalk`、`discord`、`slack`、`kook`、`vocechat`、`weixin_official_account`、`satori`、`misskey`、`line`。

### 1.3 Star 基类 & 最小示例

```python
from astrbot.api.star import Context, Star
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """指令描述（会显示在帮助中）"""
        user_name = event.get_sender_name()
        yield event.plain_result(f"Hello, {user_name}!")

    async def terminate(self):
        """插件停用/热重载时触发，用于清理资源"""
```

约定：
- 必须继承 `Star`，`__init__` 接收 `Context`（若带配置则再接收 `AstrBotConfig`）。
- Handler 前两个参数固定为 `self, event`。
- 使用 `astrbot.api.logger` 打印日志。

---

## 2. 监听消息事件（filter 装饰器）

导入：`from astrbot.api.event import filter, AstrMessageEvent`

### 2.1 指令类装饰器

```python
# 普通指令
@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent): ...

# 带参数（自动按类型解析）
@filter.command("add")
def add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"Result: {a + b}")

# 指令组（子指令）
@filter.command_group("math")
def math(self):
    pass

@math.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"Result: {a + b}")

# 别名（v3.4.28+）
@filter.command("help", alias={"帮助", "helpme"})
def help_cmd(self, event: AstrMessageEvent): ...

# 正则
@filter.regex(r"^hi.*")
async def on_hi(self, event: AstrMessageEvent): ...
```

### 2.2 过滤器装饰器（可叠加，AND 关系）

```python
# 事件类型
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
@filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
@filter.event_message_type(filter.EventMessageType.ALL)

# 平台限制
@filter.platform_adapter_type(
    filter.PlatformAdapterType.AIOCQHTTP |
    filter.PlatformAdapterType.QQOFFICIAL
)

# 权限
@filter.permission_type(filter.PermissionType.ADMIN)

# 优先级（默认 0，数字越大越先执行）
@filter.command("foo", priority=1)
```

### 2.3 生命周期 / LLM 钩子

```python
@filter.on_astrbot_loaded()           # AstrBot 启动完成 (v3.4.34+)
async def on_loaded(self): ...

@filter.on_waiting_llm_request()      # 等待 LLM 响应时
async def on_waiting(self, event): await event.send("🤔")

@filter.on_llm_request()              # 修改发往 LLM 的请求
async def hook_req(self, event, req: ProviderRequest):
    req.system_prompt += "自定义提示"

@filter.on_llm_response()             # LLM 返回后
async def hook_resp(self, event, resp: LLMResponse): ...

@filter.on_decorating_result()        # 发送前修改结果
async def on_decorate(self, event):
    result = event.get_result()
    result.chain.append(Plain("!"))

@filter.after_message_sent()          # 消息发送后
async def after_sent(self, event): ...
```

### 2.4 AstrMessageEvent 常用 API

| 方法 / 属性 | 作用 |
|---|---|
| `event.message_str` | 纯文本消息内容 |
| `event.get_messages()` | 完整消息链组件列表 |
| `event.message_obj` | 底层消息对象 |
| `event.get_sender_id()` / `get_sender_name()` | 发送者 ID / 昵称 |
| `event.get_group_id()` | 群组 ID |
| `event.get_platform_name()` | 平台名（如 `aiocqhttp`） |
| `event.unified_msg_origin` | 会话唯一标识（主动推送用） |
| `event.is_at_or_wake_command()` | 是否被 @ 或触发唤醒词 |
| `event.is_admin()` | 是否管理员 |
| `event.plain_result(text)` / `image_result(...)` / `chain_result(...)` / `make_result()` | 构造返回结果 |
| `event.get_result()` | 获取当前结果对象 |
| `event.send(message)` | 直接发送消息 |
| `event.stop_event()` | 终止事件冒泡 |

---

## 3. 发送消息

### 3.1 被动回复（yield 生成器）

```python
@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
    yield event.image_result("path/to/image.jpg")
    yield event.image_result("https://example.com/image.jpg")
```

### 3.2 构造消息链

```python
import astrbot.api.message_components as Comp

chain = [
    Comp.At(qq=event.get_sender_id()),
    Comp.Plain("文本内容"),
    Comp.Image.fromURL("https://example.com/a.jpg"),
    Comp.Image.fromFileSystem("path/to/a.jpg"),
    Comp.Record(file="path/to/a.wav"),         # 仅支持 WAV
    Comp.Video.fromFileSystem(path="v.mp4"),
    Comp.Video.fromURL(url="https://..."),
    Comp.File(file="path/to/f.txt", name="f.txt"),
    Comp.Node(uin=10001, name="用户", content=[...]),  # OneBot 合并转发
]
yield event.chain_result(chain)
```

OneBot v11 专属：`Face`、`Node`、`Nodes`、`Poke`。

### 3.3 主动推送消息

```python
from astrbot.api.event import MessageChain

message_chain = (
    MessageChain()
    .message("Hello!")
    .file_image("path/to/a.jpg")
)
await self.context.send_message(event.unified_msg_origin, message_chain)
```

`unified_msg_origin` 是跨平台会话唯一 ID，可持久化后供后续主动推送使用。

---

## 4. 插件配置（_conf_schema.json）

### 4.1 Schema 示例

```json
{
  "token": {
    "description": "Bot Token",
    "type": "string",
    "obvious_hint": true
  },
  "sub_config": {
    "description": "嵌套配置",
    "type": "object",
    "items": {
      "name": { "type": "string", "description": "名称" },
      "time": { "type": "int",    "default": 123   }
    }
  }
}
```

支持类型：`string`、`text`（大文本框）、`int`、`float`、`bool`、`object`、`list`、`dict`、`template_list`、`file`。

字段属性：`type`（必填）、`description`、`hint`、`obvious_hint`、`default`、`items`（嵌套）、`invisible`、`options`（下拉）、`editor_mode`/`editor_language`/`editor_theme`（v3.5.10+ 代码编辑器）、`_special`（v4.0.0+：`select_provider` / `select_persona` / `select_knowledgebase` 等）。

v4.13.0+ 支持 `type: "file"` 上传文件：
```json
{ "demo_files": { "type": "file", "file_types": ["pdf", "docx"] } }
```

### 4.2 在代码中读取配置

```python
from astrbot.api import AstrBotConfig
from astrbot.api.star import Context, Star

class ConfigPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config           # 是一个 Dict 的子类
        # 修改后持久化
        self.config.save_config()
```

自动存储路径：`data/config/<plugin_name>_config.json`。schema 变动时自动补默认值、清理废弃键、递归更新嵌套结构。

---

## 5. 调用 AI / LLM

### 5.1 直接调用 LLM

```python
umo = event.unified_msg_origin
provider_id = await self.context.get_current_chat_provider_id(umo=umo)
llm_resp = await self.context.llm_generate(
    chat_provider_id=provider_id,
    prompt="Hello, world!",
)
```

### 5.2 注册 Function Tool

装饰器方式：
```python
@filter.llm_tool(name="get_weather")
async def get_weather(self, event: AstrMessageEvent, location: str) -> MessageEventResult:
    '''获取天气信息。

    Args:
        location(string): 地点
    '''
```

类方式：
```python
@dataclass
class BilibiliTool(FunctionTool[AstrAgentContext]):
    name: str = "bilibili_videos"
    description: str = "Fetch Bilibili videos."
    parameters: dict = Field(default_factory=lambda: {...})

    async def call(self, ctx: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        return "result"

self.context.add_llm_tools(BilibiliTool())
```

### 5.3 Agent 工具循环

```python
llm_resp = await self.context.tool_loop_agent(
    event=event,
    chat_provider_id=prov_id,
    prompt="...",
    tools=ToolSet([BilibiliTool()]),
    max_steps=30,
    tool_call_timeout=60,
)
```

### 5.4 会话 / 人格管理

```python
conv_mgr = self.context.conversation_manager
curr_cid = await conv_mgr.get_curr_conversation_id(uid)
conversation = await conv_mgr.get_conversation(uid, curr_cid)

await conv_mgr.add_message_pair(
    cid=curr_cid,
    user_message=UserMessageSegment(content=[TextPart(text="hi")]),
    assistant_message=AssistantMessageSegment(content=[TextPart(text=llm_resp.completion_text)]),
)

persona_mgr = self.context.persona_manager
persona = await persona_mgr.get_persona(persona_id)
```

其他方法：`new_conversation`、`switch_conversation`、`delete_conversation`、`get_conversations`、`update_conversation`。

---

## 6. 存储

### 6.1 简易 KV（v4.9.2+，插件间隔离）

```python
await self.put_kv_data("greeted", True)
greeted = await self.get_kv_data("greeted", default=False)
await self.delete_kv_data("greeted")
```

### 6.2 大文件 / 自定义存储目录

```python
from pathlib import Path
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

plugin_data_path = Path(get_astrbot_data_path()) / "plugin_data" / self.name
```

约定：持久化数据必须写入 `data/plugin_data/<plugin_name>/`，不要写到插件自身目录，否则会在更新时丢失。

---

## 7. 会话控制器（多轮对话）

```python
import astrbot.api.message_components as Comp
from astrbot.core.utils.session_waiter import session_waiter, SessionController

@filter.command("成语接龙")
async def handle_idiom(self, event: AstrMessageEvent):
    try:
        yield event.plain_result("请发送一个成语~")

        @session_waiter(timeout=60, record_history_chains=False)
        async def idiom_waiter(controller: SessionController, event: AstrMessageEvent):
            idiom = event.message_str
            if idiom == "退出":
                await event.send(event.plain_result("已退出~"))
                controller.stop()
                return
            if len(idiom) != 4:
                await event.send(event.plain_result("必须是四字成语~"))
                return

            result = event.make_result()
            result.chain = [Comp.Plain("先见之明")]
            await event.send(result)
            controller.keep(timeout=60, reset_timeout=True)

        try:
            await idiom_waiter(event)
        except TimeoutError:
            yield event.plain_result("你超时了！")
        finally:
            event.stop_event()
    except Exception as e:
        logger.error(str(e))
```

`SessionController`：`keep(timeout, reset_timeout)`、`stop()`、`get_history_chains()`。

自定义会话分组（例如按群聊而不是按个人）：
```python
class CustomFilter(SessionFilter):
    def filter(self, event: AstrMessageEvent) -> str:
        return event.get_group_id() or event.unified_msg_origin

await idiom_waiter(event, session_filter=CustomFilter())
```

---

## 8. 杂项 / 进阶

### 8.1 获取平台实例

```python
from astrbot.api.platform import AiocqhttpAdapter
platform = self.context.get_platform(filter.PlatformAdapterType.AIOCQHTTP)
assert isinstance(platform, AiocqhttpAdapter)
```

### 8.2 调用 OneBot 协议 API

```python
if event.get_platform_name() == "aiocqhttp":
    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
    assert isinstance(event, AiocqhttpMessageEvent)
    client = event.bot
    await client.api.call_action("delete_msg", message_id=event.message_obj.message_id)
```

参考：Napcat <https://napcat.apifox.cn/>、Lagrange <https://lagrange-onebot.apifox.cn/>。

### 8.3 插件 / 平台发现

```python
plugins = self.context.get_all_stars()                 # List[StarMetadata]
platforms = self.context.platform_manager.get_insts()  # List[Platform]
```

---

## 9. 开发规范

- 使用异步 HTTP 库（`aiohttp` / `httpx`），不要用同步的 `requests`。
- 使用 `ruff` 格式化代码。
- 持久化数据必须放 `data/plugin_data/<plugin_name>/`，不要写到插件自身目录。
- 提供良好的错误处理与日志。
- 修改代码后可在 WebUI 的插件管理 → `...` → 「重载插件」热重载。
- 优先给已有插件提 PR，而非创建重复功能。
- 依赖声明遵循 pip requirements 文件格式。

---

## 10. 快速起步模板

```python
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star

class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        """打招呼"""
        yield event.plain_result(f"Hi, {event.get_sender_name()}!")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("admin_only")
    async def admin_only(self, event: AstrMessageEvent):
        yield event.plain_result("仅管理员可用")

    async def terminate(self):
        logger.info("plugin terminated")
```

对应 `metadata.yaml`：
```yaml
display_name: MyPlugin
support_platforms:
  - aiocqhttp
astrbot_version: ">=4.16,<5"
```

对应 `_conf_schema.json`：
```json
{
  "token": { "type": "string", "description": "API Token", "obvious_hint": true }
}
```
