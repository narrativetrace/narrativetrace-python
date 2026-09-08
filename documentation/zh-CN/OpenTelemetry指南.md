<!-- source: documentation/guides/opentelemetry.md blob 8c80d624163c | translated: 2026-09-03 | reviewed: 2026-09-03 -->

# OpenTelemetry

`narrativetrace-otel` 将你的叙事以 OpenTelemetry span 的形式发出——一次捕获同时得到人类可读的
追踪和后端关联信息。它只依赖 `opentelemetry-api`。

## 批量导出(已完成的树)

```python
from opentelemetry import trace
from narrativetrace_otel import TraceSpanExporter

TraceSpanExporter(trace.get_tracer("orders")).export(context.capture_trace().roots)
```

每个节点都会变成一个嵌套 span,带有 `narrative.class`/`narrative.method`、带类型的
`narrative.param.<name>` 属性、`narrative.outcome`、`narrative.duration_ms`、并发相关属性,以及
**每个** span 上都有的 `nt.*` 模式属性。

## 实时流式传输(每个事件一个 span)

将 `OtelTraceEventListener` 挂接到管道上,即可在每次进入时打开一个 span,并在匹配的退出时关闭它,
以**事件时间戳**(而非处理时间)为锚点。孤儿 span(有进入无退出)会被一个有边界的 `PerishableMap`
清除,并以错误状态结束。

```python
from narrativetrace_otel import OtelTraceEventListener

listener = OtelTraceEventListener(trace.get_tracer("orders"))
# 从捕获管道中喂给它 TraceEvent
```

## 属性词汇表

追踪级别的键(仅根 span):`narrative.service.name/version/environment`、
`narrative.http.method/route`、`narrative.client_ip`、`narrative.enduser.id`、
`narrative.session.id`、`narrative.tenant.id`。身份字段以及 `nt.entryType`/`nt.schemaVersion` 出现在
每个 span 上,因此任何一个 span 都可以独立完成关联。
