<!-- source: documentation/guides/fastapi-asgi.md blob 1ce7dac68ee1 | translated: 2026-09-09 | reviewed: 2026-09-09 -->

# FastAPI / ASGI

`narrativetrace-asgi` envolve qualquer aplicação ASGI para que cada requisição HTTP seja capturada
como um trace e exportada no limite da requisição com o código de status e a duração reais.

```python
from fastapi import FastAPI
from narrativetrace import ContextVarNarrativeContext, trace_object
from narrativetrace_asgi import NarrativeTraceMiddleware, get_narrative_context

context = ContextVarNarrativeContext()
app = FastAPI()

@app.get("/orders/{customer_id}")
def place_order(customer_id: str):
    ctx = get_narrative_context()          # o contexto com escopo de requisição
    service = trace_object(OrderService(), ctx)
    return {"result": service.place_order(customer_id, "prod-42")}

app.add_middleware(NarrativeTraceMiddleware, context=context, exporter=my_exporter)
```

## Garantias

- **À prova de falhas** — extractores de usuário/requisição ou exportadores que lançam exceção nunca
  fazem a requisição falhar nem escondem a exceção própria do handler; o erro do handler continua se
  propagando (e exporta o status 500).
- **Árvores vazias não são exportadas**; `excluded_paths` ignora o tracing por completo.
- **Isolamento entre requisições concorrentes** — cada requisição roda em seu próprio escopo de
  contextvars, então um `asyncio.gather` de N requisições nunca se contamina entre si.

## traceparent W3C

O `traceparent` de entrada é adotado como o id de trace da requisição. Para chamadas
servidor a servidor, injete-o na saída em um cliente `httpx` — um cliente assíncrono precisa do
hook assíncrono, `attach_traceparent_async` (`httpx.AsyncClient` faz `await` em cada hook de
requisição; o `None` retornado pelo hook síncrono não pode ser aguardado):

```python
import httpx
from narrativetrace_asgi import attach_traceparent_async

client = httpx.AsyncClient(event_hooks={"request": [attach_traceparent_async]})
```

Já um `httpx.Client` síncrono combina com o `attach_traceparent` síncrono:

```python
client = httpx.Client(event_hooks={"request": [attach_traceparent]})
```

Veja o exemplo executável [`examples/fastapi_service`](../../examples/fastapi_service).
