<!-- source: documentation/guides/fastapi-asgi.md blob 1ce7dac68ee1 | translated: 2026-09-09 | reviewed: 2026-09-09 -->

# FastAPI / ASGI

`narrativetrace-asgi` 会包装任意 ASGI 应用,让每个 HTTP 请求被捕获为一条追踪,并在请求边界处
以真实的状态码和耗时导出。

```python
from fastapi import FastAPI
from narrativetrace import ContextVarNarrativeContext, trace_object
from narrativetrace_asgi import NarrativeTraceMiddleware, get_narrative_context

context = ContextVarNarrativeContext()
app = FastAPI()

@app.get("/orders/{customer_id}")
def place_order(customer_id: str):
    ctx = get_narrative_context()          # 请求作用域的上下文
    service = trace_object(OrderService(), ctx)
    return {"result": service.place_order(customer_id, "prod-42")}

app.add_middleware(NarrativeTraceMiddleware, context=context, exporter=my_exporter)
```

## 保证

- **故障安全** —— 抛出异常的用户/请求提取器或导出器永远不会使请求失败,也永远不会掩盖处理函数
  自身的异常;处理函数的错误依然会向外传播(并导出状态码 500)。
- **空树不会被导出**;`excluded_paths` 会完全绕过追踪。
- **并发请求隔离** —— 每个请求运行在自己的 contextvars 作用域中,因此 N 个请求的
  `asyncio.gather` 永远不会相互污染。

## W3C traceparent

入站的 `traceparent` 会被采纳为该请求的追踪 id。对于服务间调用,可以在出站的 `httpx` 客户端上
注入它 —— 异步客户端需要异步钩子 `attach_traceparent_async`(`httpx.AsyncClient` 会对每个请求钩子
执行 `await`,而同步钩子返回的 `None` 无法被 await):

```python
import httpx
from narrativetrace_asgi import attach_traceparent_async

client = httpx.AsyncClient(event_hooks={"request": [attach_traceparent_async]})
```

同步的 `httpx.Client` 则应搭配同步的 `attach_traceparent`:

```python
client = httpx.Client(event_hooks={"request": [attach_traceparent]})
```

参见可运行示例 [`examples/fastapi_service`](../../examples/fastapi_service)。
