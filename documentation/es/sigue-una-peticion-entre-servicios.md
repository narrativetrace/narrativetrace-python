<!-- source: documentation/recipes/follow-one-request-across-services.md blob 1b6072965043 | translated: 2026-10-18 | reviewed: - -->

# Sigue una petición entre servicios (trazado distribuido)

## El problema

> El checkout llama al servicio de pagos por HTTP. Cuando un pedido sale mal,
> quiero seguir una sola petición a través de ambos — no dos logs que tenga que
> alinear a mano.

Dos servicios, dos ficheros de log, dos conjuntos de ids. Lo que los convierte
en una sola historia es un único valor que viaja con la petición: la cabecera
W3C
[`traceparent`](https://www.w3.org/TR/trace-context/#traceparent-header).
Quien llama envía la traza en la que está; quien recibe adopta ese id de traza
en lugar de empezar una traza propia. Abajo hay una ejecución de exactamente
eso, con las líneas de ambos servicios en un solo fichero.

## Configuración mínima

Además de la [instalación](guia-de-instalacion.md) — `narrativetrace` para el
wrapper y el puente de `logging`, `narrativetrace-asgi` para las dos mitades de
la cabecera, y `httpx` para la llamada — quien llama necesita
`NarrativeTraceMiddleware` (es lo que le dice al hook de salida en qué traza
está la petición) y un hook de petición en su cliente. Quien recibe necesita la
mitad de entrada, y qué código es depende de cómo esté construido:

| El receptor es | La mitad de entrada es |
|---|---|
| Una aplicación ASGI (FastAPI, Starlette) | `NarrativeTraceMiddleware`, que adopta la cabecera por ti ([guía de FastAPI / ASGI](guia-de-fastapi-asgi.md)) |
| Cualquier otra cosa — un `http.server` simple, un framework de handlers | Unas pocas líneas en lo primero que se ejecute por petición: reset, `adopt_trace_id(parsed.trace_id, parsed.span_id)` sobre la cabecera ya analizada, servir |

El servicio de pagos de esta página es la segunda fila: el proyecto de checkout
funciona sin framework, así que el handler lee la cabecera él mismo. Es además
el ejemplo más honesto de lo que hace el middleware, porque es la misma
secuencia.

Las líneas de log salen del puente de `logging`, como en
[Añade logging a este servicio](anade-registro-a-este-servicio.md), y se
escriben en el instante en que ocurre cada llamada (un contexto cuyo store
entrega cada evento a un `LoggingTraceConsumer`, el camino en vivo de la
[Guía de logging](guia-de-logging.md)), porque en esta página lo importante es
*qué servicio escribió una línea, y mientras el otro trabajaba*. El formato de
esta página pone el id de traza en bruto en cada línea, porque el id de traza
es lo que se está siguiendo:

```python
SERVICES_FORMAT = "%(levelname)-5s [%(name)s] [%(traceId)s] - %(message)s"
```

## El escenario

**El lado de quien llama: un hook.** El `PaymentService` del checkout es ahora
un cliente HTTP. Es un cliente `httpx` ordinario con `attach_traceparent` como
hook de petición; el hook lee la traza en la que está la petición actual y
establece una cabecera — todo lo demás es una petición ordinaria:

```python
"""The checkout's payment collaborator when the payment service is a different process."""

from __future__ import annotations

import httpx
from narrativetrace_asgi import attach_traceparent

from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.services import PaymentService

_DECLINED_STATUS = 402


class HttpPaymentService(PaymentService):
    """Charges a card by POSTing to the payment service's ``endpoint``.

    The outbound half of cross-service correlation, in the shape any ``httpx`` client copies:
    ``attach_traceparent`` is a request hook that stamps the current request's trace id and calling
    span onto the call as a W3C ``traceparent`` header. The body is a comma-separated line rather
    than JSON on purpose -- this class exists to show the header, and a parser would be the only
    thing a reader had to skip.
    """

    def __init__(self, endpoint: str) -> None:
        super().__init__()
        self._endpoint = endpoint
        self._client = httpx.Client(event_hooks={"request": [attach_traceparent]})

    def charge(self, customer_id: str, amount_cents: int, card: str) -> str:
        response = self._client.post(
            self._endpoint, content=f"{customer_id},{amount_cents},{card}".encode()
        )
        if response.status_code == _DECLINED_STATUS:
            raise PaymentDeclinedError(response.text)
        return response.text

    def close(self) -> None:
        self._client.close()
```

**El lado de quien recibe: su propio contexto.** El servicio de pagos es un
segundo servicio, lo que significa un segundo contexto de narrativa — creado
con su propio nombre de logger, para que un mismo fichero de log pueda
distinguir a los dos
(`examples/recipes/checkout/payment_service_process.py`):

```python
        self.context = ContextVarNarrativeContext(
            store=LoggingEventStore(logging.getLogger(LOGGER_NAME))
        )
        self._payments = trace_object(PaymentService(), self.context)
```

**El lado de quien recibe: adoptar, servir, capturar, reiniciar.** Esta es toda
la mitad de entrada, en el mismo fichero — y la misma secuencia que realiza
`NarrativeTraceMiddleware` para una aplicación ASGI:

```python
    def handle(self, exchange: BaseHTTPRequestHandler) -> None:
        header = exchange.headers.get("traceparent")
        self.inbound_traceparent = header
        self.context.reset()
        parsed = parse_traceparent(header)
        if parsed is not None:
            self.context.adopt_trace_id(parsed.trace_id, parsed.span_id)
        try:
            length = int(exchange.headers["Content-Length"])
            customer_id, amount_cents, card = exchange.rfile.read(length).decode().split(",", 2)
            reply(exchange, 200, self._payments.charge(customer_id, int(amount_cents), card))
        except PaymentDeclinedError as declined:
            reply(exchange, 402, str(declined))
        finally:
            self.last_trace = self.context.capture_trace()
            self.context.reset()
```

**La ejecución.** El checkout es un servicio Starlette detrás de
`NarrativeTraceMiddleware`, con el cliente HTTP donde antes estaba el servicio
de pagos local, manejado con `TestClient` con el propio `traceparent` del
usuario final. El servicio de pagos es un `HTTPServer` de loopback en el mismo
proceso: la petición cruza de verdad un socket y la cabecera llega de verdad
como cabecera, que es de lo que trata esta página — un segundo proceso añadiría
un segundo intérprete y no demostraría nada más:

```python
"""documentation/recipes/follow-one-request-across-services.md's scenario: the checkout charges a
card through a second service over HTTP, the W3C ``traceparent`` goes with the request, and the
payment service's own trace carries the caller's trace id (rule 8, docs as tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs it in its own pytest process so the
log file the page embeds holds this scenario alone. The checkout is a Starlette app behind
``NarrativeTraceMiddleware`` -- the request integration the caller needs for ``attach_traceparent``
to know which trace it is in -- driven by ``TestClient`` with the end user's own ``traceparent``.
"""

import logging
import os
from pathlib import Path

from narrativetrace_asgi import NarrativeTraceMiddleware, RequestContext, parse_traceparent
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from examples.recipes.checkout import correlation_logging
from examples.recipes.checkout.env import ARTIFACTS_ENV
from examples.recipes.checkout.http_payment_service import HttpPaymentService
from examples.recipes.checkout.live_logging import LoggingEventStore
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.payment_service_process import PaymentServiceProcess
from examples.recipes.checkout.services import InventoryService, OrderRepository
from narrativetrace import ContextVarNarrativeContext, MarkdownRenderer, TraceTree, trace_object
from narrativetrace.render import StructuralTraceRenderer

# The trace the end user's request arrives in, fixed so the page's embedded artifacts name the same
# trace every run. A real client sends whatever its own tracing generated.
DEMO_TRACEPARENT = "00-c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7-c4e1d0a7c4e1d0a7-01"
SCENARIO = "A customer checks out against the payment service"

correlation_logging.install(correlation_logging.SERVICES_FORMAT)


class CapturedRequest:
    """The exporter the middleware hands the finished tree to, kept for the test to read."""

    tree: TraceTree | None = None

    def export(self, tree: TraceTree, request_context: RequestContext) -> None:
        self.tree = tree


def checkout_app(
    context: ContextVarNarrativeContext,
    exporter: CapturedRequest,
    stock: InventoryService,
    repository: OrderRepository,
    payment_endpoint: str,
) -> Starlette:
    """The checkout as a service: one route, the HTTP payment client where the local one was."""

    async def place_order(request: Request) -> JSONResponse:
        inventory = trace_object(stock, context)
        client = HttpPaymentService(payment_endpoint)
        payments = trace_object(client, context, class_name="PaymentService")
        orders = trace_object(repository, context)
        checkout = trace_object(OrderService(inventory, payments, orders), context)
        try:
            order_id = checkout.place_order("C-1234", "SKU-KB", 2, "4242424242424242")
        finally:
            client.close()
        return JSONResponse({"order_id": order_id})

    middleware = [Middleware(NarrativeTraceMiddleware, context=context, exporter=exporter)]
    return Starlette(
        routes=[Route("/checkout", place_order, methods=["POST"])], middleware=middleware
    )


def test_a_customer_checks_out_against_the_payment_service() -> None:
    caller = ContextVarNarrativeContext(
        store=LoggingEventStore(logging.getLogger("narrativetrace"))
    )
    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()
    exporter = CapturedRequest()

    with PaymentServiceProcess() as payment_service:
        app = checkout_app(caller, exporter, stock, repository, payment_service.endpoint)
        response = TestClient(app).post("/checkout", headers={"traceparent": DEMO_TRACEPARENT})

    assert response.json() == {"order_id": "ORD-C-1234-SKU-KB-2"}
    assert len(repository.saved()) == 1
    write_artifacts(exporter.tree, payment_service.last_trace)
    assert_the_trace_crossed_the_wire(payment_service, exporter.tree)


def assert_the_trace_crossed_the_wire(
    payment_service: PaymentServiceProcess, caller: TraceTree | None
) -> None:
    """One trace id, two services, one parent link: the header named the caller's trace and its
    ``charge`` span, and the payment service's root adopted both instead of starting a trace of
    its own."""
    sent = parse_traceparent(payment_service.inbound_traceparent)
    assert sent is not None
    assert str(sent.trace_id) == DEMO_TRACEPARENT.split("-")[1]

    assert payment_service.last_trace is not None
    callee_root = payment_service.last_trace.roots[0]
    assert callee_root.signature.method_name == "charge"
    assert callee_root.span_context is not None
    assert callee_root.span_context.trace_id == sent.trace_id
    # The parent crosses the wire too: the header's parent-id field names the caller's client
    # span, and the payment service's root records it as its parent.
    assert caller is not None
    client_span = caller.roots[0].children[1]
    assert client_span.signature.method_name == "charge"
    assert client_span.span_context is not None
    assert sent.span_id == client_span.span_context.span_id
    assert callee_root.span_context.parent_span_id == client_span.span_context.span_id


def write_artifacts(caller: TraceTree | None, callee: TraceTree | None) -> None:
    """The caller's value-free structure and the payment service's own narrative, into the
    directory the page embeds from."""
    assert caller is not None
    assert callee is not None
    target = Path(os.environ[ARTIFACTS_ENV])
    target.mkdir(parents=True, exist_ok=True)
    (target / "checkout.nt").write_text(
        StructuralTraceRenderer().render_document(caller, SCENARIO), encoding="utf-8"
    )
    (target / "payment-service.md").write_text(MarkdownRenderer().render(callee), encoding="utf-8")
```

## La salida real

**Las líneas de ambos servicios, en un solo fichero** — las de quien llama bajo
`narrativetrace`, las del servicio de pagos bajo `narrativetrace.payments`:

```text
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [narrativetrace.payments] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [narrativetrace.payments] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "PAY-C-1234-7998"
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "PAY-C-1234-7998"
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "ORD-C-1234-SKU-KB-2"
```

**La traza propia de quien llama,** el artefacto estructural libre de valores
de esa ejecución — los span ids de abajo son los que usa esta página para
leerla:

```text
scenario: A customer checks out against the payment service

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) → value
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) → value
  #1.3 - OrderRepository.save(order) → value
```

**La narrativa propia del servicio de pagos,** capturada por su propio contexto
al final de la petición y renderizada junto a la de quien llama:

```text
- **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) → `"PAY-C-1234-7998"` — 0ms #1
```

## Cómo leerlo

- **Un id de traza, en las líneas de ambos servicios.**
  `c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7` es el segundo corchete de cada línea de
  arriba, tanto las de quien llama como las de quien recibe. El de quien llama
  es la traza en la que está esta ejecución (la cabecera del usuario final la
  nombró); el de quien recibe es ese mismo id porque lo *adoptó*. Nada los
  correlaciona después — nunca estuvieron separados.
- **Los dos servicios se distinguen por el logger, no por el id.**
  `[narrativetrace]` es el checkout, `[narrativetrace.payments]` es el servicio
  de pagos, porque su contexto se construyó con un logger de ese nombre. Las
  dos líneas del servicio de pagos quedan *entre* el `→ PaymentService.charge`
  del checkout y su `← returned`, que es el orden en que ocurrieron las cosas:
  el checkout esperaba mientras el otro servicio trabajaba.
- **El `#1.2` de quien llama y el `#1` de quien recibe son el mismo trabajo,
  visto desde ambos extremos.** En la narrativa de quien llama,
  `#1.2 PaymentService.charge` es el span *cliente*: empieza cuando el checkout
  llama al cliente y termina cuando vuelve la respuesta, así que incluye todo
  el viaje de ida y vuelta. En la narrativa del servicio de pagos,
  `#1 PaymentService.charge` es el span *servidor*: el trabajo que realmente
  hizo. Los span ids son por árbol de traza y cada servicio numera los suyos
  desde `#1` — lo que une es el id de traza, no el número.
- **Lo que se afirma, porque una línea de log no puede mostrarlo.** El fixture
  de arriba lee la cabecera que el servicio de pagos recibió de verdad y
  comprueba tres cosas: que lleva el id de traza de quien llama, que el span
  raíz del servicio de pagos lleva ese mismo id, y que se cumple el enlace
  padre de abajo. Esa aserción es la prueba de esta página.
- **El id del span padre viaja también.** El campo de id padre de la cabecera
  `traceparent` lleva el span `charge` de quien llama, y la raíz del servicio de
  pagos lo registra como su id de span padre, así que un backend que dibuja una
  sola cascada a partir de los ids de span padre la dibuja a través de los dos
  servicios. El fixture lo afirma: el padre de la cabecera es el id del span
  cliente de quien llama, y el padre de la raíz del callee es el de la cabecera.
  El padre es solo un id: nombra un span de la traza de quien llama y nunca
  aparece como span en el árbol del propio servicio de pagos.
- **Cómo unirlos en una búsqueda de logs.** El id de traza está en cada
  registro que NarrativeTrace escribe, en cualquiera de los dos servicios,
  como atributo `traceId`. Pon `%(traceId)s` en tu formato (como arriba) o un
  formateador JSON delante, y una petición a través de ambos servicios es
  `grep c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7` — o, en el agregador que uses,
  `traceId:"c4e1…"`. El *nombre* de traza por el que
  [Añade logging a este servicio](anade-registro-a-este-servicio.md) hace grep
  se deriva del mismo id, así que también sirve como clave de búsqueda, y lo
  lee mejor una persona.
- **Las dos narrativas siguen siendo dos.** Los spans del servicio de pagos
  están en la traza del servicio de pagos, no en la de quien llama:
  `capture_trace()` en cualquiera de los lados devuelve el trabajo de ese lado.
  Un id de traza, dos árboles — que es exactamente lo que tienes en
  producción, donde el otro servicio es otro proceso en otro host.
- **Por qué se incrusta el `.nt` de quien llama y no su Markdown.** El
  renderizador Markdown marca cualquier llamada de más de 200 ms, y un viaje
  HTTP real puede cruzar esa línea en una máquina cargada, así que el Markdown
  de la traza de quien llama no es estable byte a byte. La traza estructural
  libre de valores sí lo es, y es el artefacto que lleva los span ids por los
  que se lee esta página.

## Qué no se captura

- **Un salto por un servicio que no reenvía la cabecera rompe la cadena.** La
  correlación es cooperativa: la cadena se sostiene mientras cada servicio de
  ella *pase `traceparent` adelante*. Un proxy, un consumidor de cola o un
  servicio de terceros que descarta la cabecera deja al siguiente servicio con
  NarrativeTrace sin nada que adoptar, y este empieza una traza nueva —
  correctamente, porque no tiene un padre honesto al que nombrar. Un servicio
  sin NarrativeTrace en absoluto no importa *si* reenvía la cabecera que
  recibió.
- **No se envía ninguna cabecera fuera de una petición trazada.**
  `attach_traceparent` lee el contexto que `NarrativeTraceMiddleware` enlaza
  para la petición; una llamada hecha desde un script, un worker o un hook de
  arranque no tiene ninguno, y el cliente no envía nada en lugar de una
  cabecera que apunte a una traza que no existe. Una llamada sin traza desde el
  checkout, por tanto, no se puede unir, y es a propósito. Una petición que ya
  lleva un `traceparent` propio se deja como está.
- **Solo `traceparent`.** El cliente de arriba no envía `tracestate` ni
  baggage: nada en este camino lee ni escribe estado de proveedor, y ningún
  valor de la aplicación cruza la red por culpa del trazado.
- **Nada vuelve.** La respuesta no lleva cabecera de traza, así que la
  narrativa de quien llama dice lo que envió y lo que recibió, nunca lo que
  hizo quien recibe por dentro. La narrativa propia de quien recibe es el
  registro de eso, y el id de traza es lo que la encuentra.
- **Dos servicios, un intérprete, un socket.** Lo que esta ejecución no ejerce
  es un segundo proceso, un segundo entorno y una red que pueda fallar. El
  mecanismo de la cabecera no cambia por ninguno de ellos; los modos de fallo
  de la llamada en sí son los de tu cliente HTTP.

**La skill para esto:** `narrativetrace-verify` — un cambio que cruza
servicios es exactamente el caso para el que existe: escribe la intención,
ejecuta el camino real más pequeño y lee la traza contra ella antes de darlo
por terminado.
