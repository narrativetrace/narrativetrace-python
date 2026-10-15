<!-- source: documentation/recipes/review-a-complex-flow-before-changing-it.md blob fb581f90f1a3 | translated: 2026-10-11 | reviewed: - -->

# Revise um fluxo complexo antes de alterá-lo

## O problema

> Antes de mexer no checkout, me diga o que ele realmente faz.

Ler o código-fonte responde o que ele *pode* fazer. Uma execução responde o que
ele *faz* com essas entradas — em que ordem, com quais valores, e onde o fluxo
sai do código que você está prestes a editar. Esta página deliberadamente nunca
mostra a implementação: esse é o ponto de ler uma execução.

## Configuração mínima

Nada além da [instalação](guia-de-instalacao.md) para os dois artefatos de
trace. As linhas de log precisam de um trecho de configuração comum do
`logging`, exatamente como em [Adicione logs a este serviço](adicione-logs-a-este-servico.md).
O nível de captura é uma única configuração, e `SUMMARY` é o que esta página usa
ao lado do `DETAIL` padrão:

```bash
NARRATIVETRACE_LEVEL=SUMMARY uv run pytest   # OFF | ERRORS | SUMMARY | NARRATIVE | DETAIL
```

Veja [Guia de configuração, nível de tracing](guia-de-configuracao.md).

## O cenário

Uma execução representativa do fluxo — um teste existente é o mais barato de
emprestar, e este é esse teste:

```python
"""One successful checkout, the flow
documentation/recipes/review-a-complex-flow-before-changing-it.md is read before changing anything.

A fixture because two readers need the same run under different settings: ``recipe_artifacts.py``
runs it in its own pytest process once at DETAIL and once at SUMMARY. It passes either way --
nothing here fails by design. The log lines are the same flow through the project's own ``logging``
setup (``conftest.py``).
"""

from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, export_to_logger, trace_object

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_a_customer_buys_two_keyboards(narrative_trace: ContextVarNarrativeContext) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, "4242424242424242")

    export_to_logger(narrative_trace.capture_trace())

    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert stock.available_units("SKU-KB") == 3
    assert len(repository.saved()) == 1
```

## A saída real

**Em `DETAIL`** (o padrão), `narrative-traces/traces/checkout_review_fixture/test_a_customer_buys_two_keyboards.md`:

```text
---
type: trace
run: meaty pier walks
scenario: Test a customer buys two keyboards
entry_point: OrderService.place_order
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 4
error_count: 0
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test a customer buys two keyboards
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) → `"PAY-C-1234-7998"` — 0ms #1.2
  - **OrderRepository.save**(order: `Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998)`) → `null` — 0ms #1.3
  - → `"ORD-C-1234-SKU-KB-2"`
```

**Em `SUMMARY`**, a mesma execução do mesmo teste:

```text
---
type: trace
run: quiet nib trims
scenario: Test a customer buys two keyboards
entry_point: OrderService.place_order
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 4
error_count: 0
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test a customer buys two keyboards
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: ``, sku: ``, quantity: ``, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: ``, quantity: ``) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: ``, amount_cents: ``, card: ``) → `"PAY-C-1234-7998"` — 0ms #1.2
  - **OrderRepository.save**(order: ``) → `null` — 0ms #1.3
  - → `"ORD-C-1234-SKU-KB-2"`
```

**O log que o mesmo fluxo gravou** pelo logger do próprio projeto, com valores e
tudo:

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

**O trace estrutural dessa execução**, `narrative-traces/structural/checkout_review_fixture/test_a_customer_buys_two_keyboards.nt`:

```text
scenario: Test a customer buys two keyboards

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) → value
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) → value
  #1.3 - OrderRepository.save(order) → value
```

## Como ler

**O fluxo, a partir do artefato `DETAIL`.** `#1` é a chamada que o teste fez e a
única raiz: tudo o que está indentado sob ela aconteceu dentro dela, na ordem
impressa. `#1.1` reserva duas unidades antes de qualquer cobrança; `#1.2` cobra
7998 — duas unidades a 3999, então o preço é derivado da quantidade e não passado
como argumento; `#1.3` salva um pedido que já carrega o id que `#1` retorna. Lido
como uma frase: este checkout reserva primeiro, cobra em segundo, salva em
terceiro, e o id do pedido é gerado antes do save. Uma mudança que cobre antes de
reservar, ou salve antes de cobrar, é uma mudança *nisto*, e agora você sabe
disso sem confiar em um comentário.

**Para que serve cada nível.** `DETAIL` carrega os valores dos parâmetros, e é o
que você lê enquanto trabalha no fluxo. Em `SUMMARY`, todo valor de parâmetro
fica vazio — os crases não contêm nada — porque foi suprimido na captura, não
escondido na renderização, e só raízes e chamadas-folha são mantidas; este fluxo
tem dois níveis de profundidade, então nenhum frame é intermediário e as mesmas
quatro chamadas aparecem. Um fluxo mais profundo perde o meio. Os valores de
retorno sobrevivem em todos os níveis ativos: o retorno é a carga útil de uma
narrativa. Use `SUMMARY` onde a forma e os resultados são o que você precisa e os
valores são custo — uma execução de CI, um soak longo — e `OFF`/`ERRORS` em
produção até precisar de mais.

**Qual saída um humano lê, e qual um agente lê.** As linhas de log são para o
humano de plantão: elas se intercalam com tudo o mais que o serviço registra,
carregam os valores e são indexadas pelo nome do trace — `[solid wand romps]` —
de modo que um checkout pode ser extraído com grep de um arquivo movimentado. O
`.nt` é para o agente e o revisor: **sem valores por construção** — compare-o com
a linha de log acima e a diferença não é que os valores foram substituídos, mas
que nunca foram gravados. `(customer_id, sku, quantity, card_number)` são os
*nomes* dos parâmetros; `→ value` diz que um valor foi retornado sem dizer qual
(em `reserve` e `save` é o `None` do Python, que ainda assim conta — não existe
`void`). É isso que o torna seguro para commitar, para comparar em uma revisão e
para entregar a um modelo: ele não pode vazar um id de cliente, e não muda quando
os dados mudam — só quando as *chamadas* mudam. Fixá-lo é
[Revise uma refatoração: o comportamento mudou](revise-uma-refatoracao-o-comportamento-mudou.md).

## O que não é capturado

- **Chamadas dentro de objetos não envolvidos.** Quatro objetos foram envolvidos;
  uma chamada entre dois objetos por trás deles, ou um método privado, nunca
  aparece. Um fluxo que parece raso pode ser profundo.
- **O que a integração escolhida não intercepta.** `trace_object` só vê chamadas
  feitas *através* do wrapper: uma chamada interna que um objeto faz a si mesmo
  (`self._helper()`) é invisível para ele, enquanto um decorador nesse método a
  veria. [Escolhendo uma integração](escolhendo-uma-integracao.md) traz o
  trade-off por caminho, e esta é a parte dele que muda o que você pode ler aqui.
- **Trabalho que saiu da thread.** Uma chamada entregue a um executor sem o
  contexto não viaja mais longe; o trace termina onde a thread terminou.
- **Valores que a deny-list ou a regra de formato de valor pegou**, aqui
  `card_number` e `card`, aparecem como `[REDACTED]` tanto no log quanto no
  artefato `DETAIL`, e estão ausentes por construção do `.nt`.
- **Uma execução, não o contrato.** Outra entrada toma outro caminho — um sku sem
  estoque nunca chega a `#1.2`.

**A skill para isto:** `narrativetrace-verify` — ela escreve a intenção primeiro,
roda o menor caminho real e lê o trace sem valores contra essa intenção antes de
qualquer coisa ser dada como pronta.
