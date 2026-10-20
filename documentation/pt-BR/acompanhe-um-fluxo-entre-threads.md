<!-- source: documentation/recipes/follow-a-flow-across-threads.md blob 37880c006918 | translated: 2026-10-18 | reviewed: - -->

# Acompanhe um fluxo entre threads

## O problema

> O checkout entrega as partes lentas a um pool de threads. O trace para no
> submit e não consigo ver o que o trabalho em segundo plano fez.

Uma thread não sabe nada sobre o trace em que outra thread está, então
entregar trabalho a um pool entrega o trabalho e mais nada. O trace também
precisa ser entregue — explicitamente, no momento do submit. Abaixo estão uma
execução que faz isso e uma que não faz.

## Configuração mínima

Nada além da [instalação](guia-de-instalacao.md): `ForkJoinGroup` e
`FireAndForgetGroup` estão em `narrativetrace`, ao lado do próprio contexto.
Qual usar depende do que quem chama faz em seguida:

| A chamada que dispara | O helper | O passo final |
|---|---|---|
| Espera o trabalho em segundo plano (esta página) | `ForkJoinGroup` | `merge()`, depois que as tarefas terminam — ele enxerta o que elas gravaram sob o span que as disparou |
| Retorna sem esperar | `FireAndForgetGroup` | Nenhum. Os filhos são um registro separado, lido por `child_roots()` |

Para corrotinas, os mesmos grupos recebem `await group.run_async(lambda: …)` no
lugar de `wrap(...)`. A [seção Concurrency do README](../../README.md#concurrency)
é a versão curta de ambos.

As linhas de log são gravadas no instante em que cada chamada acontece (um
contexto cujo store entrega cada evento a um `LoggingTraceConsumer`, o caminho
ao vivo do [Guia de logging](guia-de-logging.md)), com a thread e o trace id
bruto no formato — nesta página a coluna da thread é metade da história:

```python
THREADS_FORMAT = "%(levelname)-5s [%(threadName)s] [%(name)s] [%(traceId)s] - %(message)s"
```
Dois registros no log desta página não tratam de uma chamada — o fork e o join
—, então não carregam trace id, e um formato que cita `traceId` lançaria
exceção neles. Um pequeno filtro, que um projeto que registra essas linhas
escreve uma única vez:

```python
class TraceIdOrBlank(logging.Filter):
    """The fork and join lines belong to no span, so they carry no ``traceId``: print a blank
    rather than let the format raise."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.setdefault("traceId", "")
        return True


```
## O cenário

**O checkout, com os dois passos lentos fora da sua própria thread.** A
entrega é `group.wrap(...)` em volta de cada tarefa e `group.merge()` depois
que as duas terminam:

```python
"""The checkout with the two slow steps off the caller's thread, for
documentation/recipes/follow-a-flow-across-threads.md."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any

from examples.recipes.checkout.domain import Order, PaymentDeclinedError
from examples.recipes.checkout.fraud import RuleBasedFraudCheck
from examples.recipes.checkout.order_service import UNIT_PRICE_CENTS
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ForkJoinGroup, NarrativeContext


class ParallelCheckout:
    """Reserves the stock and runs the fraud check on an executor, waits for both, then charges
    and saves.

    A task handed to an executor runs on a thread that knows nothing about the caller's trace, so
    the trace has to be handed over with it: ``group.wrap`` takes a snapshot at submission time,
    the worker activates it, and ``group.merge()`` grafts what the worker recorded back under the
    span that launched it. Every forked task must be wrapped and ``merge()`` must run after they
    finish, or the children stay detached from the caller's trace.
    """

    def __init__(
        self,
        context: NarrativeContext,
        inventory: InventoryService,
        fraud: RuleBasedFraudCheck,
        payments: PaymentService,
        orders: OrderRepository,
        workers: ThreadPoolExecutor,
    ) -> None:
        self._context = context
        self._inventory = inventory
        self._fraud = fraud
        self._payments = payments
        self._orders = orders
        self._workers = workers

    def place_order(self, customer_id: str, sku: str, quantity: int, card_number: str) -> str:
        amount_cents = UNIT_PRICE_CENTS * quantity

        group = ForkJoinGroup.create(self._context)
        reserved = self._workers.submit(group.wrap(lambda: self._inventory.reserve(sku, quantity)))
        approved = self._workers.submit(
            group.wrap(lambda: self._fraud.approve(customer_id, amount_cents))
        )
        tasks: list[Future[Any]] = [reserved, approved]
        wait(tasks)  # the merge may only run after both are done
        group.merge()

        reserved.result()  # a task's own failure is the caller's, raised here
        if not approved.result():
            self._inventory.release(sku, quantity)
            raise PaymentDeclinedError("the fraud check refused the order")
        self._payments.charge(customer_id, amount_cents, card_number)
        order_id = f"ORD-{customer_id}-{sku}-{quantity}"
        self._orders.save(Order(order_id, customer_id, sku, quantity, amount_cents))
        return order_id
```
**A execução — e o mesmo trabalho sem a entrega.** O segundo teste submete uma
chamada rastreada ao mesmo pool sem grupo e sem wrap, que é como o código era
antes de a entrega ser adicionada:

```python
"""documentation/recipes/follow-a-flow-across-threads.md's scenario: the two tasks the checkout
hands to an executor stay inside the caller's trace when they are wrapped, and a task submitted
without the handover starts a trace of its own (rule 8, docs as tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs the first test alone for the log
the page embeds (the second one's trace id is freshly generated on every run, which is the finding
it reports and the one thing no embedded block can hold) and the second test in a run of its own.
One worker thread, named: the page embeds a real run's log byte for byte, and two threads logging
at once interleave differently every time. The handover is identical either way.
"""

import logging
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from examples.recipes.checkout import correlation_logging
from examples.recipes.checkout.env import ARTIFACTS_ENV
from examples.recipes.checkout.fraud import RuleBasedFraudCheck
from examples.recipes.checkout.live_logging import LoggingEventStore
from examples.recipes.checkout.parallel_checkout import ParallelCheckout
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, TraceNode, trace_object
from narrativetrace.render import StructuralTraceRenderer

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")

correlation_logging.install(correlation_logging.THREADS_FORMAT)


@pytest.fixture
def context() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext(store=LoggingEventStore(logging.getLogger("narrativetrace")))


@pytest.fixture
def workers() -> Iterator[ThreadPoolExecutor]:
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="checkout-worker")
    yield pool
    pool.shutdown(wait=True)


def test_the_background_tasks_stay_in_the_customers_trace(
    context: ContextVarNarrativeContext, workers: ThreadPoolExecutor
) -> None:
    context.adopt_trace_id(DEMO_TRACE_ID)
    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()
    checkout = parallel_checkout(context, stock, repository, workers)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, "4242424242424242")

    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert stock.available_units("SKU-KB") == 3
    assert len(repository.saved()) == 1
    assert_the_children_came_home(context)
    write_structural_trace(context)


def assert_the_children_came_home(context: ContextVarNarrativeContext) -> None:
    """The merged children are under the span that launched them, in the caller's own trace."""
    root = context.capture_trace().roots[0]
    assert names(root.children) == [
        "InventoryService.reserve",
        "FraudCheckService.approve",
        "PaymentService.charge",
        "OrderRepository.save",
    ]
    reserve = root.children[0]
    assert reserve.span_context is not None
    assert root.span_context is not None
    assert reserve.span_context.trace_id == root.span_context.trace_id
    assert reserve.span_context.parent_span_id == root.span_context.span_id
    assert reserve.concurrency is not None
    assert reserve.concurrency.thread_name == "checkout-worker_0"


def test_a_task_submitted_without_the_handover_starts_a_new_trace(
    context: ContextVarNarrativeContext, workers: ThreadPoolExecutor
) -> None:
    context.adopt_trace_id(DEMO_TRACE_ID)
    stock = InventoryService("SKU-KB", 5)
    inventory = trace_object(stock, context)

    def reserve_and_report_the_trace() -> TraceId:
        inventory.reserve("SKU-KB", 2)
        return context.trace_id()

    # No ForkJoinGroup, no snapshot: the task is handed over, the trace is not.
    on_the_worker = workers.submit(reserve_and_report_the_trace).result()

    assert stock.available_units("SKU-KB") == 3
    assert on_the_worker != context.trace_id()
    assert "InventoryService.reserve" not in names(context.capture_trace().roots)


def parallel_checkout(
    context: ContextVarNarrativeContext,
    stock: InventoryService,
    repository: OrderRepository,
    workers: ThreadPoolExecutor,
) -> ParallelCheckout:
    inventory = trace_object(stock, context)
    fraud = trace_object(RuleBasedFraudCheck(), context, class_name="FraudCheckService")
    payments = trace_object(PaymentService(), context)
    orders = trace_object(repository, context)
    checkout = ParallelCheckout(context, inventory, fraud, payments, orders, workers)
    return trace_object(checkout, context, class_name="OrderService")


def names(nodes: list[TraceNode]) -> list[str]:
    return [f"{node.signature.class_name}.{node.signature.method_name}" for node in nodes]


def write_structural_trace(context: ContextVarNarrativeContext) -> None:
    """The caller's value-free structure, into the directory the page embeds from."""
    target = Path(os.environ[ARTIFACTS_ENV])
    target.mkdir(parents=True, exist_ok=True)
    document = StructuralTraceRenderer().render_document(
        context.capture_trace(), "The background tasks stay in the customers trace"
    )
    (target / "checkout.nt").write_text(document, encoding="utf-8")
```
## A saída real

**O log da execução que mantém o trace:**

```text
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [MainThread] [narrativetrace] [] - ⑂ fork group created [groupId: fork-1]
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → FraudCheckService.approve(customer_id: "C-1234", amount_cents: 7998)
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: True
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → FraudCheckService.approve(customer_id: "C-1234", amount_cents: 7998)
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: True
DEBUG [MainThread] [narrativetrace] [] - ⑃ fork joined [groupId: fork-1, members: 2]
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "PAY-C-1234-7998"
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "ORD-C-1234-SKU-KB-2"
```
**O trace estrutural dessa execução:**

```text
scenario: The background tasks stay in the customers trace

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) → value
  ~ fork [2]
    #1.1 - FraudCheckService.approve(customer_id, amount_cents) → value
    #1.2 - InventoryService.reserve(sku, quantity) → value
  #1.3 - PaymentService.charge(customer_id, amount_cents, card) → value
  #1.4 - OrderRepository.save(order) → value
```
O mesmo trace renderizado como Markdown (o que o plugin do pytest grava para um
teste que usa a fixture `narrative_trace`) traz mais três coisas — o nome da
thread de trabalho junto de cada filho, o tempo de relógio do join e uma dica
"sequential async" onde as tarefas não se sobrepuseram — e não é embutido aqui
porque os números dentro dele mudam a cada execução.

## Como ler

- **A entrega é visível, duas vezes.**
  `⑂ fork group created [groupId: fork-1]` é o grupo sendo criado, antes de
  qualquer tarefa ser submetida; `⑃ fork joined [groupId: fork-1, members: 2]`
  é o `merge()` informando o que voltou. Entre os dois está o trabalho em
  segundo plano que pertence a este checkout. Essas duas linhas carregam um
  trace id vazio — o último colchete é `[]` — porque não são eventos de span:
  são o ciclo de vida do próprio grupo, publicado pelo contexto e não por uma
  chamada rastreada.
- **As linhas dos filhos carregam o trace id do cliente, na thread de
  trabalho.** `InventoryService.reserve` e `FraudCheckService.approve` são
  escritos a partir de `[checkout-worker_0]` com
  `[c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7]` — o mesmo id de toda linha `[MainThread]`
  acima e abaixo delas. Esse é o snapshot que o `group.wrap` tirou no momento
  do submit, ativado na thread de trabalho.
- **Cada filho aparece duas vezes no log, e uma vez no trace.** O primeiro par
  é o trabalho acontecendo, em `checkout-worker_0`. O segundo par — as mesmas
  duas chamadas, os mesmos valores, em `MainThread`, logo antes da linha do
  join — é o `merge()` republicando-as sob o span que as disparou, que é o que
  as coloca na árvore de quem chamou. Leia o log como log: duas gravações, um
  evento cada. Leia o `.nt` como o registro: `#1.1` e `#1.2` sob `#1`, dentro
  de `~ fork [2]`, exatamente uma vez.
- **O id de span pai de cada filho é o span que o disparou.** `#1.1` e `#1.2`
  citam `#1` como pai — não porque rodaram sob ele na mesma thread (não
  rodaram), mas porque o grupo os enxertou ali. Uma linha de log não consegue
  mostrar isso como um valor estável (um id de span é gerado por span e mudaria
  a cada execução), então `assert_the_children_came_home`, acima, o afirma: o
  `parent_span_id` de cada filho é o `span_id` da raiz, o `trace_id` de cada
  filho é o da raiz, e a thread registrada é `checkout-worker_0`. Essa asserção
  é a prova desta página.
- **Como a segunda execução difere.** Submeta a mesma chamada rastreada sem
  wrap e a thread de trabalho não tem snapshot para ativar, então a sua
  primeira chamada rastreada faz o que toda primeira chamada rastreada faz:
  inicia um trace. O segundo teste afirma as duas consequências — o trace id
  observado *na thread de trabalho* não é o de quem chamou, e o trace capturado
  de quem chamou não contém nenhum `InventoryService.reserve`. O trabalho
  acontece do mesmo jeito, o estoque é reservado do mesmo jeito, as linhas são
  registradas do mesmo jeito. Só que são a história de outra pessoa, sob um id
  que ninguém está procurando. O log dessa execução não é embutido pelo mesmo
  motivo: o id em suas linhas é novo a cada vez, e esse é o achado.
- **Por que "awaited sequentially" é o diagnóstico certo aqui.** O pool deste
  cenário tem uma thread, então as duas tarefas de fato rodam uma depois da
  outra e a renderização em Markdown diz isso. Essa é uma propriedade deste
  cenário, escolhida para que o log de uma execução seja estável byte a byte o
  bastante para ser embutido — não da entrega, que é o mesmo código para um
  pool de qualquer tamanho.

## O que não é capturado

- **Trabalho iniciado sem a entrega inicia um novo trace.** Essa é toda a
  segunda metade desta página: sem wrap, sem snapshot, sem trace id
  compartilhado. Nada avisa você, porque do ponto de vista da biblioteca uma
  thread nova com uma chamada rastreada é um trace novo comum.
- **Um framework que propaga contexto por conta própria só é coberto onde a sua
  integração diz.** O middleware ASGI vincula o contexto da requisição à task
  da própria requisição; o trabalho que você empurra de um handler para um pool
  de threads continua sendo seu para envolver. Fora do que o
  [Guia de funcionalidades](guia-de-funcionalidades.md) lista, presuma que a
  entrega é sua para escrever.
- **`capture_trace()` informa o trace do contexto em que é chamado.** Uma
  captura feita de dentro da pilha de uma thread de trabalho vê os spans dessa
  thread, não os de quem chamou — por isso é o grupo, e não a consulta, que
  junta os dois.
- **Um grupo sem `merge()` não coleta nada no trace de quem chamou.** Os filhos
  são gravados, e depois nada os enxerta: o log ainda os mostra (com o trace id
  certo), a árvore de quem chamou não.
- **Trabalho que sobrevive à chamada é outro helper.** `FireAndForgetGroup` não
  tem passo de merge por desenho — o método que disparou já retornou, então não
  sobrou ninguém em quem fazer o merge.
- **Intercalação.** Com um pool real, as linhas dos filhos chegam na ordem em
  que as threads forem escalonadas, e por isso um log é lido por trace id e não
  por posição. Os artefatos de trace não são afetados: a paternidade vem do
  snapshot, não da ordem em que as linhas foram gravadas.

**A skill para isto:** `narrativetrace-verify` — "runs async" e "crosses
threads" são dois dos casos para os quais ela existe, e ela lê o trace
estrutural contra a intenção antes que qualquer coisa seja dada como pronta.
