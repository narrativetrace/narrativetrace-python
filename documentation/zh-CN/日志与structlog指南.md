<!-- source: documentation/guides/logging.md blob 28814dbf375e | translated: 2026-09-03 | reviewed: 2026-09-03 -->

# 日志与 structlog

NarrativeTrace 会桥接到标准库的 `logging` 框架以及 `structlog`,并从两者中发出*相同*的规范关联键。

## 标准库 logging

分为两部分:

- `LoggingTraceConsumer` —— 一个事件消费者,在 `DEBUG` 级别记录进入/返回,在 `WARNING` 级别记录
  异常(`!! {type}: {message} [{error_context}]`,已做控制字符清理)。
- `NarrativeContextFilter` —— 一个日志 `Filter`,会把当前作用域的键(`traceId`、`traceName`、
  `spanId`、`nt.class`、`nt.method`、`nt.depth`、服务身份、请求/用户键)盖印到每一条日志记录上。

```python
import logging
from narrativetrace import NarrativeContextFilter

handler = logging.StreamHandler()
handler.addFilter(NarrativeContextFilter())
logging.getLogger().addHandler(handler)
```

## 请求级作用域

在一次 HTTP 请求内部,ASGI 中间件会打开一个 `request_log_scope(...)`,让请求相关的键
(`httpMethod`、`httpRoute`、`clientIp`、用户身份)搭载在任何活跃的方法作用域之下。

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
