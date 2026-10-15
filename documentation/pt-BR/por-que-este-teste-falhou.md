<!-- source: documentation/recipes/why-did-this-test-fail.md blob 2d305deb9ab7 | translated: 2026-10-11 | reviewed: - -->

# Por que este teste falhou

## O problema

> Por que este teste falhou?

Um teste do checkout está vermelho. A asserção diz o que não bateu; ela não diz
o que o código fez no caminho até ali, que é a parte de que você precisa para
saber se o errado é o código ou a expectativa.

## Configuração mínima

Nada além da [instalação](guia-de-instalacao.md). A fixture `narrative_trace` do
[`narrativetrace-pytest`](guia-de-pytest.md) grava uma narrativa por teste sem
nenhuma configuração — inclusive para um teste que falha, que é o caso desta
página. Os arquivos caem em `narrative-traces/traces/<module>/<test>.md`, e
`narrative-traces/manifest.json` lista todos os artefatos de todos os cenários
quando você sabe o nome do teste mas não o do arquivo dele.

## O cenário

O teste que falha:

```python
"""The failing checkout test documentation/recipes/why-did-this-test-fail.md is read through. It
fails on an assertion, by design, which is why it is a fixture (not collected as a ``test_*``
module): ``recipe_artifacts.py`` runs it in its own pytest process and records what the run
reported.

Nothing here says which side is wrong -- that is the reader's exercise, and the narrative the run
writes is what settles it. Do not add a comment that gives it away.
"""

from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, trace_object

# A fixed trace id, so the page's embedded artifact names the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_the_customer_gets_an_order_id_for_their_keyboards(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    inventory = trace_object(InventoryService("SKU-KB", 5), narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(OrderRepository(), narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, "4242424242424242")

    assert order_id == "ORD-C-1234-SKU-KB-1"
```

## A saída real

O que o runner reportou:

```text
assert 'ORD-C-1234-SKU-KB-2' == 'ORD-C-1234-SKU-KB-1'
  
  - ORD-C-1234-SKU-KB-1
  ?                   ^
  + ORD-C-1234-SKU-KB-2
  ?                   ^
```

E o que a mesma execução gravou ao lado, em
`narrative-traces/traces/stale_expectation_fixture/test_the_customer_gets_an_order_id_for_their_keyboards.md`:

```text
---
type: trace
run: neat wheel lands
scenario: Test the customer gets an order id for their keyboards
entry_point: OrderService.place_order
duration_ms: 2
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 4
error_count: 0
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test the customer gets an order id for their keyboards
**Duration:** 2ms | **Result:** FAILED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 2ms #1
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) → `"PAY-C-1234-7998"` — 0ms #1.2
  - **OrderRepository.save**(order: `Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998)`) → `null` — 0ms #1.3
  - → `"ORD-C-1234-SKU-KB-2"`
```

## Como ler

Leia a narrativa de cima para baixo contra a asserção, um span de cada vez:

- `#1 OrderService.place_order(... quantity: 2 ...) → "ORD-C-1234-SKU-KB-2"`.
  O valor que a asserção rejeitou está bem ali, e a entrada que o produziu
  também: a chamada pediu **dois** teclados.
- `#1.1 InventoryService.reserve(sku: "SKU-KB", quantity: 2)` — duas unidades
  reservadas, de acordo com a chamada.
- `#1.2 PaymentService.charge(..., amount_cents: 7998, ...)` — 7998 são duas
  unidades a 3999, então o preço também concorda com a quantidade.
- `#1.3 OrderRepository.save(order: Order(... quantity=2 ...))` — o que foi
  armazenado concorda com o que foi pedido.
- `**Result:** FAILED` no cabeçalho é o veredito do *teste*, não do código:
  `error_count: 0` e todos os spans foram concluídos. Nada lançou exceção.

Todo span concorda com todo outro span e com a chamada que os iniciou. A
expectativa — `ORD-C-1234-SKU-KB-1` — é a única coisa na execução que diz um
teclado, então é ela que está desatualizada; a fixture contra a qual foi escrita
mudou desde então para pedir dois. A correção está no teste.

A leitura oposta é a outra receita: quando um span *discorda* da intenção — uma
quantidade que muda entre duas chamadas, uma chamada que deveria ter seguido e
não seguiu — o código é que está errado, e
[Ajude-me a depurar e corrigir este bug](ajude-me-a-depurar-e-corrigir-este-bug.md)
é esse passo a passo.

## O que não é capturado

- **Só a execução daquele teste.** A narrativa é gravada por teste, por
  execução. Uma falha que acontece uma vez a cada vinte execuções precisa que
  uma dessas execuções seja a que gravou o arquivo; cada execução sobrescreve o
  arquivo da anterior, e uma execução que falha não avança de forma alguma o
  baseline `.nt` sem valores.
- **A asserção não está no trace.** As duas saídas acima vêm de dois lugares — o
  runner reportou a divergência, o plugin gravou o fluxo — e nada as correlaciona
  automaticamente além do nome do cenário.
- **Um valor que um teste calculou mas nunca passou a uma chamada rastreada é
  invisível.** O trace carrega parâmetros e valores de retorno de chamadas
  envolvidas, não variáveis locais.
- **Os tempos em uma execução que falhou não significam nada.** A execução
  deixou de ser representativa no momento em que a asserção lançou a exceção.

**A skill para isto:** `narrativetrace-debug` — ela parte do sintoma, lê o
primeiro span em que um valor diverge e o nomeia pelo id do span.
