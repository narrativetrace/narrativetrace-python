<!-- source: documentation/recipes/send-traces-to-the-observability-stack-you-already-run.md blob b7d969c29603 | translated: 2026-10-18 | reviewed: - -->

# Envie os traces para o stack de observabilidade que você já tem

## O problema

> Já temos tracing e dashboards. Não vou adotar um segundo lugar para olhar —
> isto pode entrar no stack que a gente já roda?

Pode: uma execução, dois consumidores. As linhas da narrativa continuam indo
para o seu logger, e os mesmos eventos viram spans do OpenTelemetry na saída.
Abaixo está um checkout com as duas saídas lado a lado.

## Configuração mínima

`narrativetrace-otel` (a sua [linha de instalação está na página de instalação](guia-de-instalacao.md))
mais a API do OpenTelemetry, que o pacote deixa por sua conta para que a versão
do seu SDK prevaleça. Há duas formas de entrar, e a diferença é *quando* um
span existe:

| Modo | Classe | Use quando |
|---|---|---|
| Ao vivo, enquanto os métodos rodam | `OtelTraceEventListener` | Você quer spans no seu collector mesmo que o processo morra no meio da requisição — esta página |
| Em lote, depois do fato | `TraceSpanExporter` | Você quer os spans de uma árvore de trace já concluída, exportados uma vez, ao menor custo de execução: `TraceSpanExporter(tracer).export(context.capture_trace().roots)` |

Qualquer um dos dois é ligado por você, no seu próprio código: o contexto
recebe o event store para o qual deve entregar os eventos, e um store que
também entrega cada evento a um consumidor é como um segundo consumidor se
junta ao primeiro ([Guia de OpenTelemetry](guia-de-opentelemetry.md)). Um
exportador em memória faz as vezes do seu collector abaixo, o que também é o
retrato mais claro do que a sua ligação real faz com um de verdade.

## O cenário

O store é a única ideia nova: ele entrega cada evento à narração que você já
tem e ao listener do OpenTelemetry, e o guarda para o `capture_trace()` como
qualquer store. O checkout em si é envolvido exatamente como em todas as outras
páginas:

```python
"""documentation/recipes/send-traces-to-the-observability-stack-you-already-run.md's scenario: ONE
run of the checkout writes the log lines it always wrote AND an OpenTelemetry span per traced call,
with the parentage and the attributes the page shows -- and without the redacted values (rule 8,
docs as tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs it in its own pytest process so the
log file the page embeds holds this scenario alone. No ``narrative_trace`` fixture, deliberately:
this page's subject is the context a deployment composes -- the narration it already has and an
OpenTelemetry listener, fed from one event store -- and an in-memory exporter stands in for the
collector. The exported spans are written out by ``write_exported_spans``, naming and sorting
everything it prints, so one run's dump is byte-identical to the next: a raw span dump carries
timestamps and OpenTelemetry's own generated ids and could never be embedded.
"""

import os
from pathlib import Path

from narrativetrace_otel import OtelTraceEventListener
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from examples.recipes.checkout.env import ARTIFACTS_ENV
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import (
    ContextVarNarrativeContext,
    LoggingTraceConsumer,
    TraceEvent,
    TraceId,
    trace_object,
)
from narrativetrace.pipeline.event_store import EventStore

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")
CARD_NUMBER = "4242424242424242"


# snippet:begin wiring
class NarratedAndExportedStore(EventStore):
    """Hands every event to the narration and to OpenTelemetry as it happens, and keeps it for
    ``capture_trace()`` -- the one place the two consumers meet."""

    def __init__(self, narration: LoggingTraceConsumer, export: OtelTraceEventListener) -> None:
        super().__init__()
        self._narration = narration
        self._export = export

    def add(self, event: TraceEvent) -> None:
        self._narration.accept(event)
        self._export(event)
        super().add(event)


# snippet:end wiring


def test_one_run_narrates_and_exports() -> None:
    spans = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    store = NarratedAndExportedStore(
        LoggingTraceConsumer(), OtelTraceEventListener(provider.get_tracer("narrativetrace"))
    )
    context = ContextVarNarrativeContext(store=store)
    context.adopt_trace_id(DEMO_TRACE_ID)
    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()
    inventory = trace_object(stock, context)
    payments = trace_object(PaymentService(), context)
    orders = trace_object(repository, context)
    checkout = trace_object(OrderService(inventory, payments, orders), context)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, CARD_NUMBER)

    exported = spans.get_finished_spans()
    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert_one_span_per_traced_call(exported)
    assert_no_redacted_value_was_exported(exported)
    assert_parameters_are_typed(exported)
    write_exported_spans(exported)
    provider.shutdown()


def assert_one_span_per_traced_call(exported: tuple[ReadableSpan, ...]) -> None:
    """Four traced calls, four spans, ended innermost first -- and the tree is reconstructed."""
    assert [span.name for span in exported] == [
        "InventoryService.reserve",
        "PaymentService.charge",
        "OrderRepository.save",
        "OrderService.place_order",
    ]
    by_id = {span_id(span): span for span in exported}
    root = named(exported, "OrderService.place_order")
    charge = named(exported, "PaymentService.charge")
    assert charge.parent is not None
    assert by_id[charge.parent.span_id] is root
    assert root.parent is None


def assert_no_redacted_value_was_exported(exported: tuple[ReadableSpan, ...]) -> None:
    """What the deny-list caught never reaches the exporter either -- there is no attribute for
    it, not even one holding the marker."""
    attributes = {
        key: str(value) for span in exported for key, value in (span.attributes or {}).items()
    }
    assert "narrative.param.card_number" not in attributes
    assert "narrative.param.card" not in attributes
    assert not any(CARD_NUMBER in value for value in attributes.values())


def assert_parameters_are_typed(exported: tuple[ReadableSpan, ...]) -> None:
    """``quantity: 2`` is an integer attribute, not the string ``"2"``."""
    root = named(exported, "OrderService.place_order")
    assert root.attributes is not None
    assert root.attributes["narrative.param.quantity"] == 2
    assert isinstance(root.attributes["narrative.param.quantity"], int)


def span_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return int(span.context.span_id)


def named(exported: tuple[ReadableSpan, ...], name: str) -> ReadableSpan:
    return next(span for span in exported if span.name == name)


def write_exported_spans(exported: tuple[ReadableSpan, ...]) -> None:
    """The dump the page embeds: span name, parent, and every attribute, sorted by key."""
    names = {span_id(span): span.name for span in exported}
    lines: list[str] = []
    for span in exported:
        parent = names[span.parent.span_id] if span.parent else "(none — this is the root)"
        lines += [f"span: {span.name}", f"  parent: {parent}"]
        lines += [f"    {key}: {value}" for key, value in sorted((span.attributes or {}).items())]
    target = Path(os.environ[ARTIFACTS_ENV])
    target.mkdir(parents=True, exist_ok=True)
    (target / "exported-spans.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
```
## A saída real

**As linhas de log**, inalteradas por tudo isto — a mesma narração que
[Adicione logs a este serviço](adicione-logs-a-este-servico.md) produz:

```text
DEBUG [solid wand romps] [narrativetrace] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - ← returned: "PAY-C-1234-7998"
DEBUG [solid wand romps] [narrativetrace] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - ← returned: "ORD-C-1234-SKU-KB-2"
```
**Os spans que saíram da mesma execução**, como o exportador em memória os
recebeu — nome, pai e todos os atributos, ordenados:

```text
span: InventoryService.reserve
  parent: OrderService.place_order
    narrative.class: InventoryService
    narrative.method: reserve
    narrative.outcome: null
    narrative.param.quantity: 2
    narrative.param.sku: SKU-KB
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
span: PaymentService.charge
  parent: OrderService.place_order
    narrative.class: PaymentService
    narrative.method: charge
    narrative.outcome: "PAY-C-1234-7998"
    narrative.param.amount_cents: 7998
    narrative.param.customer_id: C-1234
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
span: OrderRepository.save
  parent: OrderService.place_order
    narrative.class: OrderRepository
    narrative.method: save
    narrative.outcome: null
    narrative.param.order.amount_cents: 7998
    narrative.param.order.customer_id: C-1234
    narrative.param.order.order_id: ORD-C-1234-SKU-KB-2
    narrative.param.order.quantity: 2
    narrative.param.order.sku: SKU-KB
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
span: OrderService.place_order
  parent: (none — this is the root)
    narrative.class: OrderService
    narrative.method: place_order
    narrative.outcome: "ORD-C-1234-SKU-KB-2"
    narrative.param.customer_id: C-1234
    narrative.param.quantity: 2
    narrative.param.sku: SKU-KB
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
```
## Como ler

- **Quatro chamadas rastreadas, quatro spans, uma árvore.** Os spans chegam na
  ordem em que *terminaram* — o mais interno primeiro, a raiz por último, que é
  como qualquer pipeline OTel enxerga uma árvore concluída. A paternidade não é
  inferida dessa ordem nem de um contexto ambiente: o listener lê o
  `parent_span_id` explícito de cada evento, e por isso
  `InventoryService.reserve`, `PaymentService.charge` e `OrderRepository.save`
  citam `OrderService.place_order` como pai, ainda que tenham terminado antes
  dele.
- **O que cada span carrega.** `narrative.class` e `narrative.method` são a
  chamada; `narrative.param.<name>` é um atributo por parâmetro, tipado
  (`narrative.param.quantity: 2` é um inteiro, não a string `"2"` — a fixture
  afirma isso); `narrative.outcome` é o valor retornado como a narração o
  renderiza, de modo que um método que retornou `None` carrega
  `narrative.outcome: null`. `narrative.trace_id` e `narrative.trace_name` são
  a identidade própria do NarrativeTrace para o trace, levada como atributos
  para que um span no seu backend possa ser casado com a linha de log e o
  arquivo de trace que descrevem a mesma chamada —
  [Acompanhe uma requisição entre serviços](acompanhe-uma-requisicao-entre-servicos.md)
  é o mesmo id fazendo o mesmo trabalho através de uma fronteira de processo.
  Os atributos `nt.*` marcam o schema que esses atributos seguem e a história à
  qual a chamada pertence.
- **Um parâmetro dataclass chega achatado.** `OrderRepository.save(order)` é um
  parâmetro, e foi exportado como `narrative.param.order.order_id`,
  `narrative.param.order.customer_id`, `narrative.param.order.sku`,
  `narrative.param.order.quantity`, `narrative.param.order.amount_cents` —
  campo a campo, porque é assim que o valor foi renderizado: lendo o seu
  estado, nunca chamando o seu `__str__`.
- **A ocultação também alcança este caminho.** Não existe atributo
  `narrative.param.card_number` nem `narrative.param.card` em nenhum dos spans
  acima — não um atributo contendo `[REDACTED]`, atributo nenhum. Um valor
  negado é descartado na captura, antes de o evento existir, então nenhum
  consumidor pode recebê-lo; a fixture afirma isso, além da árvore de spans
  ([Mantenha os segredos fora dos logs](mantenha-os-segredos-fora-dos-logs.md)).
- **Qual configuração moveu qual evento para qual consumidor.** Três decisões,
  nesta ordem:
  1. O nível de tracing decide se um evento chega a ser criado. Em `SUMMARY`
     esses mesmos quatro spans são exportados *sem* os atributos
     `narrative.param.*`, porque os valores de parâmetro não são renderizados
     nesse nível; em `OFF` não há evento e, portanto, não há span — ambos são
     afirmados nos testes de receita deste repositório
     ([Trace em produção sem o custo](trace-em-producao-sem-o-custo.md)).
  2. O store decide quem vê o evento. Aqui um store entrega cada evento à
     narração, depois à exportação, e então o guarda; a retenção — o que o
     `capture_trace()` e os arquivos de trace leem — fica intocada. Nada foi
     tirado do logger para alimentar o exportador.
  3. O nível do seu logger decide o que é *impresso*. Subir o logger
     `narrativetrace` para `INFO` esvazia o bloco de log acima e não muda nada
     nos spans.
- **Por que este não é um segundo lugar para olhar.** Os spans são seus, no seu
  collector, sob o nome do seu serviço, ao lado dos spans que o seu framework já
  emite. O que o NarrativeTrace acrescenta é um span por *chamada de método
  rastreada*, com os parâmetros e o resultado nele — um nível abaixo do span
  HTTP que você já tem.

## O que não é capturado

- **O que o seu stack faz com os spans é do seu stack.** Amostragem, retenção,
  indexação e se um atributo é pesquisável são decisões do collector e do
  backend. Esta página mostra o que sai do processo; não afirma nada sobre a UI
  de nenhum fornecedor.
- **Os ids não são compartilhados.** O OpenTelemetry gera os próprios ids de
  trace e de span para os spans que cria aqui, e a identidade do NarrativeTrace
  viaja junto como os atributos `narrative.trace_id` / `narrative.trace_name`.
  A posição de um span na cascata do seu backend é do OTel; casá-lo com uma
  linha de log é trabalho do atributo.
- **Ao vivo e em lote não são os mesmos spans.** O listener desta página cria um
  span enquanto o método roda, então um órfão (uma entrada sem saída — um
  processo morto no meio da chamada) termina encerrado com status de erro pelo
  mapa limitado do próprio listener. O exportador em lote só vê árvores
  concluídas e acrescenta `narrative.duration_ms`, que o caminho ao vivo não
  tem.
- **O custo é um listener na thread de quem chama.** O store roda os dois
  consumidores inline, então a criação do span está no caminho da chamada
  rastreada. Essa é a troca por ver o span enquanto o método ainda está rodando;
  um consumidor em buffer tira isso da thread de quem chama ao preço de
  descartar eventos sob pressão, cada perda contada
  ([README, Concurrency](../../README.md#concurrency)).
- **Só o que é rastreado é exportado.** Não existe span para uma chamada que
  nenhuma integração interceptou — o caminho de exportação herda exatamente a
  fronteira do caminho de captura.

**A skill para isto:** `narrativetrace-doctor` — uma verificação de ligação por
integração de framework, e ela informa se algum sink realmente recebe o que é
rastreado.
