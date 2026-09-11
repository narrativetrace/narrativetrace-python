<!-- source: documentation/guides/fastapi-asgi.md blob 1ce7dac68ee1 | translated: 2026-09-09 | reviewed: 2026-09-09 -->

# FastAPI / ASGI

`narrativetrace-asgi` envuelve cualquier aplicación ASGI para que cada petición HTTP se capture como
una traza y se exporte en el límite de la petición con el código de estado y la duración reales.

```python
from fastapi import FastAPI
from narrativetrace import ContextVarNarrativeContext, trace_object
from narrativetrace_asgi import NarrativeTraceMiddleware, get_narrative_context

context = ContextVarNarrativeContext()
app = FastAPI()

@app.get("/orders/{customer_id}")
def place_order(customer_id: str):
    ctx = get_narrative_context()          # el contexto acotado a la petición
    service = trace_object(OrderService(), ctx)
    return {"result": service.place_order(customer_id, "prod-42")}

app.add_middleware(NarrativeTraceMiddleware, context=context, exporter=my_exporter)
```

## Garantías

- **A prueba de fallos** — los extractores de usuario/petición o los exportadores que lanzan
  excepciones nunca hacen fallar la petición ni ocultan la excepción propia del handler; el error
  del handler se sigue propagando (y se exporta con el estado 500).
- **Los árboles de trazas vacíos no se exportan**; `excluded_paths` evita el tracing por completo.
- **Aislamiento entre peticiones concurrentes** — cada petición se ejecuta en su propio ámbito de
  contextvars, por lo que un `asyncio.gather` de N peticiones nunca se contamina entre sí.

## W3C traceparent

El `traceparent` entrante se adopta como el id de traza de la petición. Para llamadas
servidor a servidor, inyéctalo saliente en un cliente `httpx` — un cliente asíncrono necesita el
hook asíncrono, `attach_traceparent_async` (`httpx.AsyncClient` hace `await` de cada hook de
petición; el `None` que devuelve el hook síncrono no se puede esperar):

```python
import httpx
from narrativetrace_asgi import attach_traceparent_async

client = httpx.AsyncClient(event_hooks={"request": [attach_traceparent_async]})
```

Un `httpx.Client` síncrono, en cambio, combina con el `attach_traceparent` síncrono:

```python
client = httpx.Client(event_hooks={"request": [attach_traceparent]})
```

Consulta el ejemplo ejecutable [`examples/fastapi_service`](../../examples/fastapi_service).
