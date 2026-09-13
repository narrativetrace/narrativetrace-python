<!-- source: documentation/guides/logging.md blob 793352c40b97 | translated: 2026-09-13 | reviewed: - -->

# 日志与 structlog

NarrativeTrace 会桥接到标准库的 `logging` 框架以及 `structlog`,并从两者中发出*相同*的规范关联键。

## 标准库 logging

分为两部分:

- `LoggingTraceConsumer` —— 一个事件消费者,在 `DEBUG` 级别记录进入/返回,在 `WARNING` 级别记录
  异常(`!! {type}: {message} [{error_context}]`,已做控制字符清理)。
- `NarrativeContextFilter` —— 一个日志 `Filter`,会把当前作用域的键(`traceId`、`traceName`、
  `spanId`、`nt.class`、`nt.method`、`nt.depth`、服务身份、请求/用户键)盖印到每一条日志记录上。
  `traceName` 和 `runName` *(since 0.1.2, unreleased)* 一旦被该 filter 处理过,就总是存在——没有
  活跃追踪/运行时为 `""`——所以引用二者之一的模式串永远不会在一条无追踪的日志行上抛出异常。

```python
import logging
from narrativetrace import NarrativeContextFilter

handler = logging.StreamHandler()
handler.addFilter(NarrativeContextFilter())
logging.getLogger().addHandler(handler)
```

## 一个流一个消费者,多个 handler

`nt.depth` 现在是每个 `LoggingTraceConsumer` 实例自己私有的计数器 *(since 0.1.2, unreleased)*,
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

*(since 0.1.2, unreleased)*——在 PyPI 上发布的 `0.1.1` 中,请改为手动通过
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

*(since 0.1.2, unreleased)* `narrativetrace-pytest` 的 `pytest_sessionstart` 钩子每个 pytest
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

## 这在示例中是如何接入的

`examples/` 下的每个可运行示例都会把它的追踪连同控制台叙述一起发送到一个按真实项目方式配置的
logger——即本指南中的组合根处的 `logging.basicConfig`,加上 `LoggingTraceConsumer`/
`NarrativeContextFilter`,而不是抄进 README 里的一段代码片段。参见
[`examples/README.md`](../../examples/README.md#where-the-logger-is-configured)
了解具体是哪个文件配置了哪个示例。
