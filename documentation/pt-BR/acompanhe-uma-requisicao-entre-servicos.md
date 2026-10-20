<!-- source: documentation/recipes/follow-one-request-across-services.md blob 1b6072965043 | translated: 2026-10-18 | reviewed: - -->

# Acompanhe uma requisição entre serviços (tracing distribuído)

## O problema

> O checkout chama o serviço de pagamento por HTTP. Quando um pedido dá errado,
> quero uma única requisição atravessando os dois — não dois logs que eu tenha
> de alinhar na mão.

Dois serviços, dois arquivos de log, dois conjuntos de ids. O que os torna uma
só história é um único valor viajando com a requisição: o header W3C
[`traceparent`](https://www.w3.org/TR/trace-context/#traceparent-header). Quem
chama envia o trace em que está; quem é chamado adota esse trace id em vez de
iniciar um trace próprio. Abaixo está uma execução exatamente disso, com as
linhas dos dois serviços em um único arquivo.

## Configuração mínima

Além da [instalação](guia-de-instalacao.md) — `narrativetrace` para o wrapper
e a ponte com o `logging`, `narrativetrace-asgi` para as duas metades do
header, e `httpx` para a chamada —, quem chama precisa do
`NarrativeTraceMiddleware` (é ele que diz ao hook de saída em que trace a
requisição está) e de um request hook no seu client. Quem é chamado precisa da
metade de entrada, e qual código ela é depende de como ele foi construído:

| O serviço chamado é | A metade de entrada é |
|---|---|
| Uma aplicação ASGI (FastAPI, Starlette) | `NarrativeTraceMiddleware`, que adota o header por você ([Guia de FastAPI / ASGI](guia-de-fastapi-asgi.md)) |
| Qualquer outra coisa — um `http.server` simples, um framework de handlers | Poucas linhas no que rodar primeiro a cada requisição: reset, `adopt_trace_id(parsed.trace_id, parsed.span_id)` sobre o header já interpretado, atender |

O serviço de pagamento desta página é a segunda linha: o projeto de checkout
roda sem framework, então o handler lê o header por conta própria. Esse também
é o exemplo honesto do que o middleware faz, já que é a mesma sequência.

As linhas de log vêm da ponte com o `logging`, como em
[Adicione logs a este serviço](adicione-logs-a-este-servico.md), e são
gravadas no instante em que cada chamada acontece (um contexto cujo store
entrega cada evento a um `LoggingTraceConsumer`, o caminho ao vivo do
[Guia de logging](guia-de-logging.md)), porque nesta página *qual serviço
escreveu uma linha, e enquanto o outro trabalhava* é o ponto. O formato desta
página coloca o trace id bruto em toda linha, porque o trace id é a coisa
que está sendo acompanhada:

```python
SERVICES_FORMAT = "%(levelname)-5s [%(name)s] [%(traceId)s] - %(message)s"
```
## O cenário

**O lado de quem chama: um hook.** O `PaymentService` do checkout agora é um
client HTTP. É um client `httpx` comum com `attach_traceparent` como request
hook; o hook lê o trace em que a requisição atual está e define um header —
todo o resto é uma requisição comum:

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
**O lado de quem é chamado: o seu próprio contexto.** O serviço de pagamento é
um segundo serviço, o que significa um segundo contexto de narrativa — criado
com um nome de logger próprio, para que um único arquivo de log possa distinguir
os dois (`examples/recipes/checkout/payment_service_process.py`):

```python
        self.context = ContextVarNarrativeContext(
            store=LoggingEventStore(logging.getLogger(LOGGER_NAME))
        )
        self._payments = trace_object(PaymentService(), self.context)
```
**O lado de quem é chamado: adotar, atender, capturar, resetar.** Esta é a
metade de entrada inteira, no mesmo arquivo — e a mesma sequência que o
`NarrativeTraceMiddleware` executa para uma aplicação ASGI:

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
**A execução.** O checkout é um serviço Starlette atrás do
`NarrativeTraceMiddleware`, com o client HTTP no lugar onde ficava o serviço de
pagamento local, conduzido por `TestClient` com o `traceparent` do próprio
usuário final. O serviço de pagamento é um `HTTPServer` em loopback no mesmo
processo: a requisição realmente atravessa um socket e o header realmente chega
como header, que é o assunto desta página — um segundo processo acrescentaria um
segundo interpretador e não provaria mais nada:

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
## A saída real

**As linhas dos dois serviços, um arquivo** — as de quem chama sob
`narrativetrace`, as do serviço de pagamento sob `narrativetrace.payments`:

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
**O trace de quem chama,** o artefato estrutural livre de valores dessa
execução — os ids de span abaixo são os pelos quais esta página lê:

```text
scenario: A customer checks out against the payment service

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) → value
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) → value
  #1.3 - OrderRepository.save(order) → value
```
**A narrativa do próprio serviço de pagamento,** capturada pelo seu próprio
contexto ao fim da requisição e renderizada ao lado da de quem chama:

```text
- **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) → `"PAY-C-1234-7998"` — 0ms #1
```
## Como ler

- **Um trace id, nas linhas dos dois serviços.**
  `c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7` é o segundo colchete de toda linha acima,
  tanto as de quem chama quanto as de quem é chamado. O de quem chama é o trace
  em que esta execução está (o header do usuário final o nomeou); o de quem é
  chamado é esse mesmo id porque o *adotou*. Nada os correlaciona depois do
  fato — eles nunca estiveram separados.
- **Os dois serviços se distinguem pelo logger, não pelo id.**
  `[narrativetrace]` é o checkout, `[narrativetrace.payments]` é o serviço de
  pagamento, porque o contexto dele foi construído com um logger desse nome. As
  duas linhas do serviço de pagamento ficam *entre* o `→ PaymentService.charge`
  do checkout e o seu `← returned`, que é a ordem em que as coisas aconteceram:
  o checkout esperava enquanto o outro serviço trabalhava.
- **O `#1.2` de quem chama e o `#1` de quem é chamado são o mesmo trabalho,
  visto dos dois lados.** Na narrativa de quem chama, `#1.2 PaymentService.charge`
  é o span de *client*: começa quando o checkout chama o client e termina quando
  a resposta volta, então inclui a viagem de ida e volta inteira. Na narrativa
  do serviço de pagamento, `#1 PaymentService.charge` é o span de *servidor*: o
  trabalho que ele realmente fez. Os ids de span são por árvore de trace e cada
  serviço numera os seus a partir de `#1` — o que une é o trace id, não o
  número.
- **O que é afirmado, porque uma linha de log não consegue mostrar.** A fixture
  acima lê o header que o serviço de pagamento realmente recebeu e confere três
  coisas: ele carrega o trace id de quem chama, o span raiz do serviço de
  pagamento carrega esse mesmo id, e o vínculo de pai abaixo se sustenta. Essa
  asserção é a prova desta página.
- **O id do span pai viaja também.** O campo parent-id do header `traceparent`
  carrega o span `charge` de quem chama, e a raiz do serviço de pagamento o
  registra como seu id de span pai; assim, um backend que desenha uma única
  cascata a partir de ids de span pai a desenha através dos dois serviços. A
  fixture afirma isso: o pai do header é o id do span cliente de quem chama, e o
  pai da raiz do callee é o do header. O pai é só um id: nomeia um span do trace
  de quem chama e nunca aparece como span na árvore do próprio serviço de
  pagamento.
- **Como uni-los em uma busca de logs.** O trace id está em todo registro que o
  NarrativeTrace escreve, em qualquer um dos serviços, como o atributo
  `traceId`. Ponha `%(traceId)s` no seu formato (como acima), ou um formatter
  JSON na frente dele, e uma requisição através dos dois serviços é
  `grep c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7` — ou, no agregador que você rodar,
  `traceId:"c4e1…"`. O *nome* do trace que
  [Adicione logs a este serviço](adicione-logs-a-este-servico.md) usa no grep é
  derivado do mesmo id, então também funciona como chave de busca, e é mais
  legível para uma pessoa.
- **As duas narrativas continuam duas.** Os spans do serviço de pagamento estão
  no trace do serviço de pagamento, não no de quem chama: `capture_trace()` de
  qualquer lado devolve o trabalho desse lado. Um trace id, duas árvores — que
  é exatamente o que você tem em produção, onde o outro serviço é um processo
  diferente em um host diferente.
- **Por que o `.nt` de quem chama é embutido e não o seu Markdown.** O renderer
  de Markdown marca qualquer chamada mais lenta que 200 ms, e uma viagem HTTP
  real pode cruzar essa linha em uma máquina carregada, de modo que o Markdown
  do trace de quem chama não é estável byte a byte. O trace estrutural livre de
  valores é, e é o artefato que carrega os ids de span pelos quais esta página
  lê.

## O que não é capturado

- **Um salto por um serviço que não repassa o header quebra a cadeia.** A
  correlação é cooperativa: a cadeia se mantém enquanto todo serviço nela
  *repassar o `traceparent`*. Um proxy, um consumidor de fila ou um serviço de
  terceiros que descarta o header deixa o próximo serviço NarrativeTrace sem
  nada para adotar, e ele inicia um trace novo — corretamente, já que não tem um
  pai honesto para citar. Um serviço sem NarrativeTrace nenhum não tem problema
  *se* repassar o header que recebeu.
- **Nenhum header é enviado fora de uma requisição rastreada.**
  `attach_traceparent` lê o contexto que o `NarrativeTraceMiddleware` vincula à
  requisição; uma chamada feita de um script, de um worker ou de um hook de
  inicialização não tem nenhum, e o client não envia nada em vez de um header
  apontando para um trace que não existe. Uma chamada não rastreada saindo do
  checkout, portanto, não pode ser unida, e isso é proposital. Uma requisição
  que já traz um `traceparent` próprio é deixada como está.
- **Somente `traceparent`.** O client acima não envia `tracestate` nem baggage:
  nada neste caminho lê ou escreve estado de fornecedor, e nenhum valor da
  aplicação cruza a rede por causa do tracing.
- **Nada volta.** A resposta não carrega header de trace, então a narrativa de
  quem chama diz o que enviou e o que recebeu, nunca o que o serviço chamado
  fez por dentro. A narrativa do próprio serviço chamado é o registro disso, e o
  trace id é o que a encontra.
- **Dois serviços, um interpretador, um socket.** O que esta execução não
  exercita é um segundo processo, um segundo ambiente e uma rede que pode
  falhar. O mecanismo do header não muda por nada disso; os modos de falha da
  chamada em si são do seu client HTTP.

**A skill para isto:** `narrativetrace-verify` — uma mudança que atravessa
serviços é exatamente o caso para o qual ela existe: escreva a intenção,
execute o menor caminho real e leia o trace contra ela antes de dar a mudança
por pronta.
