<!-- source: documentation/guides/logging.md blob 8e11e0235925 | translated: 2026-09-17 | reviewed: - -->

# 日志、structlog 与 Loguru

NarrativeTrace 会桥接到标准库的 `logging` 框架以及 `structlog`,并从两者中发出*相同*的规范关联键。
Loguru 用户可以通过 Loguru 自己文档化的标准库互操作机制,到达同一条追踪——见下文的
[Loguru](#loguru)。

## 标准库 logging

分为两部分:

- `LoggingTraceConsumer` —— 一个事件消费者,在 `DEBUG` 级别记录进入/返回,在 `WARNING` 级别记录
  异常(`!! {type}: {message} [{error_context}]`,已做控制字符清理)。
- `NarrativeContextFilter` —— 一个日志 `Filter`,会把当前作用域的键(`traceId`、`traceName`、
  `spanId`、`nt.class`、`nt.method`、`nt.depth`、服务身份、请求/用户键)盖印到每一条日志记录上。
  `traceName` 和 `runName` *(since 0.1.2)* 一旦被该 filter 处理过,就总是存在——没有
  活跃追踪/运行时为 `""`——所以引用二者之一的模式串永远不会在一条无追踪的日志行上抛出异常。

```python
import logging
from narrativetrace import NarrativeContextFilter

handler = logging.StreamHandler()
handler.addFilter(NarrativeContextFilter())
logging.getLogger().addHandler(handler)
```

## 一个流一个消费者,多个 handler

`nt.depth` 现在是每个 `LoggingTraceConsumer` 实例自己私有的计数器 *(since 0.1.2)*,
所以两个实例重放*同一个*
事件流时(比如都作为 listener 挂在同一条流水线上)会各自报告正确的深度——一个不会再破坏另一个的
计数。`NarrativeContextFilter` 和 `structlog` 处理器完全不受影响:它们读取的是最内层帧共享的
类/方法/追踪身份信息,处理同一个事件的任何实例看到的都一样,而不是某个消费者自己的深度计数器。
即便如此,仍然建议每个事件流只用一个 `LoggingTraceConsumer`——这样更容易推理,而且不小心多创建
一个实例是很容易发生的(比如两段不同的配置代码各自创建了一个)。想把追踪同时发到多个地方(比如
标准输出和一个文件)?给它的 logger 加更多 `logging.Handler`,而不是加第二个消费者:

```python
logger = logging.getLogger("narrativetrace")
logger.addHandler(logging.StreamHandler())           # first destination
logger.addHandler(logging.FileHandler("trace.log"))  # second destination, same consumer
```

## `export_to_logger` —— 一次调用搞定

*(since 0.1.2)*——在 PyPI 上发布的 `0.1.1` 中,请改为手动通过
`LoggingTraceConsumer` 重放 `store.events()`。

`export_to_logger(trace, logger=None)` 会把一个已经捕获好的追踪,通过一个私有的
`LoggingTraceConsumer` 一次调用重放出去——不需要手动搭建 `EventStore`,也不需要自己写循环:

```python
from narrativetrace import ContextVarNarrativeContext, export_to_logger, trace_object

context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

export_to_logger(context.capture_trace())
```

每次调用都会打开自己的私有消费者,所以多次调用它——哪怕是从不同线程并发调用——也不会触犯上面
"一个流一个消费者"的规则。

## 请求级作用域

在一次 HTTP 请求内部,ASGI 中间件会打开一个 `request_log_scope(...)`,让请求相关的键
(`httpMethod`、`httpRoute`、`clientIp`、用户身份)搭载在任何活跃的方法作用域之下。

## 运行也有自己的 MDC 键:`runName`

*(since 0.1.2)* `narrativetrace-pytest` 的 `pytest_sessionstart` 钩子每个 pytest
会话生成一个运行 id——绝不重新派生——并调用 `set_run_name(run.name)`,让 `runName`(运行自己的
三词短语,不同于任何追踪自己的 `traceName`)在整个会话期间搭载在每一条日志行上,就像
`request_log_scope` 搭载在一个方法作用域之下一样;对应的 `pytest_sessionfinish` 钩子会再次
清除它。一个同时展示两个键的模式串:

```python
import logging

logging.basicConfig(format="%(asctime)s [%(traceName)s] [%(runName)s] %(message)s")
```

在被追踪的 pytest 会话之外——一个简单脚本,或者从其中调用的 `export_to_logger`——`runName` 为
`""`,所以同一个模式串在任何地方都是安全的。运行名称还出现在哪些地方(套件页脚、
`manifest.json`、每份 Markdown 追踪文档的 frontmatter)以及它的不变式(绝不会进入结构化 `.nt`
产物),参见[配置指南 § 运行也有名字](配置指南.md#运行也有名字)。

## structlog

`narrativetrace-structlog` 提供了一个处理器,注入完全相同的键集合:

```python
import structlog
from narrativetrace_structlog import narrative_context_processor

structlog.configure(
    processors=[narrative_context_processor, structlog.processors.JSONRenderer()]
)
```

两个前端共享 `narrativetrace.current_scope_keys()` 作为唯一的词汇来源,因此它们的键集合永远不会
出现分歧。

## Loguru

NarrativeTrace 没有为 Loguru 内置任何专门的桥接——Loguru 是一个日志库,不是叙事的来源,上面的标准
库桥接就是 Loguru 用户需要的全部机制。Loguru 自己文档化了与标准库 `logging` 的互操作方式:一个继承
自 `logging.Handler` 的 `InterceptHandler`,把标准库的每条记录重新通过 `logger` 记录一遍(见 Loguru
自己的方案,["Entirely compatible with standard
logging"](https://loguru.readthedocs.io/en/stable/overview.html))。把标准库的根 logger 指向那个
handler,再加上 `export_to_logger`——也就是 [60 秒教程"发送到你的日志系统"那一步](60秒.md#发送到你的日志系统)
里同一个一次调用的重放机制——就能不写任何 NarrativeTrace 专属代码,把追踪送到你的 Loguru sink:

```python
# main.py
import inspect  # 新增:InterceptHandler 自己的帧遍历逻辑,照抄 Loguru 的方案
import logging  # 新增:InterceptHandler 继承的标准库 logger;也是 export_to_logger 的目标
import sys  # 新增:下面 sink 的 stdout 目标

from loguru import logger  # 新增:目标 sink

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    TraceId,
    export_to_logger,  # 新增:一次调用就把已捕获的追踪重放到你的日志系统
    trace_object,
)


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


# 一个固定的追踪 id,采纳它是为了让这个页面里嵌入的输出每次都指向同一条追踪。真实的运行每次
# 都会生成一个随机的(绝不是这个——这是本 DEMO 自己的常量,不是库的默认值),生成方式与
# servlet 风格的边界处理入站追踪请求头所用的 TraceId.adopt_trace_id 机制相同。
DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")


# 新增:Loguru 自己文档化的标准库互操作方案,原样照搬——见
# https://loguru.readthedocs.io/en/stable/overview.html,"Entirely compatible with standard
# logging"。NarrativeTrace 没有为 Loguru 内置任何专门的桥接;这个方案就是全部机制——标准库 logger
# 发出的每条记录(包括 export_to_logger 发出的)都会重新通过 `logger` 记录一遍。
class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # 找到对应的 Loguru 级别(如果存在的话)。
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 找到发起这条日志的调用者所在的帧。
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# 新增:一个固定的、不带时间戳的 sink,让这个页面里嵌入的输出永远不会随时钟变化——你自己的 sink
# 保留真实的格式、颜色和轮转配置;只有这个演示需要确定性输出。
logger.remove()
logger.add(sys.stdout, format="{level} | {message}", colorize=False)
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

trace = context.capture_trace()  # 新增:只捕获一次,print 和 export 共用同一条追踪
print(IndentedTextRenderer().render(trace))

export_to_logger(trace)  # 新增:和上一步一样的一次调用导出——现在落到了 Loguru 里
```

```bash
uv run main.py
```

```text
trace: loose hook parks (a1b2c3d)

OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
DEBUG | → OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
DEBUG | ← returned: "ORD-cust-1-prod-42-3"
```

(这个演示的 sink 用 `"{level} | {message}"` 格式,是这个页面自己的选择,为了让输出不随时钟
变化;你真实的 sink 保留你已经配置好的格式、颜色和轮转。)Loguru 用户保留 Loguru 已经给他们的一切
——sink、轮转、颜色、`logger.catch`——完全不受影响;`export_to_logger` 只是把一条已经捕获好的追踪,
通过 Loguru 的 `InterceptHandler` 已经在监听的标准库桥接重放了一遍。他们不再需要写的,是业务方法
内部那一行 `logger.info(...)`(或者 `logger.debug(...)`)调用——上面这两行来自 `place_order` 自己的
名字、参数名和返回值,是代码本来就有的信息,不是谁写出来的一条日志调用。

## 这在示例中是如何接入的

`examples/` 下的每个可运行示例都会把它的追踪连同控制台叙述一起发送到一个按真实项目方式配置的
logger——即本指南中的组合根处的 `logging.basicConfig`,加上 `LoggingTraceConsumer`/
`NarrativeContextFilter`,而不是抄进 README 里的一段代码片段。参见
[`examples/README.md`](../../examples/README.md#where-the-logger-is-configured)
了解具体是哪个文件配置了哪个示例。
