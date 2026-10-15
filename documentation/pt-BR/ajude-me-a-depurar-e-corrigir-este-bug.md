<!-- source: documentation/recipes/help-me-debug-and-fix-this-bug.md blob a176672c9aac | translated: 2026-10-11 | reviewed: - -->

# Ajude-me a depurar e corrigir este bug

## O problema

> Ajude-me a depurar e corrigir este bug: o cartão de um cliente foi recusado e
> o teclado nunca voltou para o estoque.

O erro que a equipe tem é `PaymentDeclinedError: card declined by the issuer`,
que não é o bug. O bug é o que o checkout fez *depois* dele.

## Configuração mínima

Nada além da [instalação](guia-de-instalacao.md): a fixture `narrative_trace`
do [`narrativetrace-pytest`](guia-de-pytest.md) grava um trace por teste sem
nenhuma configuração. O último passo desta página — fixar o fluxo corrigido —
liga o modo de aprovação, que é uma única configuração:

```bash
NARRATIVETRACE_APPROVAL=true uv run pytest   # compara a estrutura de cada teste que passa com o trace aprovado commitado
```

Veja [Guia de configuração, artefato estrutural e modo de aprovação](guia-de-configuracao.md)
e [O que commitar](o-que-commitar.md).

## O cenário

Reproduza-o no menor teste que pode falhar por esse motivo — um cartão recusado
deve deixar o estoque como o encontrou:

```python
"""The reproduction documentation/recipes/help-me-debug-and-fix-this-bug.md is written around: a
declined card must leave the stock as it found it.

The second test is the same reproduction against the checkout as it stood before the fix
(``OrderServiceWithoutRelease``), so the page's "before" trace comes from a real failing run rather
than from prose. It FAILS by design, which is why this module is a fixture (not collected as a
``test_*`` module): ``recipe_artifacts.py`` runs it in its own pytest process and records what the
run reported.

Both tests adopt the same fixed trace id, so the two artifacts a reader compares differ only where
the code differs.
"""

import pytest

from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.order_service_without_release import OrderServiceWithoutRelease
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, trace_object

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_the_stock_is_released_when_the_card_is_declined(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    with pytest.raises(PaymentDeclinedError):
        checkout.place_order("C-1234", "SKU-KB", 2, PaymentService.DECLINING_CARD)

    assert repository.saved() == []
    assert stock.available_units("SKU-KB") == 5


def test_the_stock_is_released_when_the_card_is_declined_before_the_fix(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(
        OrderServiceWithoutRelease(inventory, payments, orders),
        narrative_trace,
        class_name="OrderService",
    )

    with pytest.raises(PaymentDeclinedError):
        checkout.place_order("C-1234", "SKU-KB", 2, PaymentService.DECLINING_CARD)

    assert repository.saved() == []
    assert stock.available_units("SKU-KB") == 5
```

O segundo teste roda a mesma reprodução contra o checkout como ele estava antes
da correção, que é a execução de onde vem o primeiro trace abaixo. (Este
repositório mantém os dois em um módulo de fixture que roda em um processo
pytest próprio, porque o segundo teste falha por design; no seu projeto, o teste
que falha é simplesmente o seu teste.)

```python
"""The same checkout with no release path: a declined charge leaves the reservation behind."""

from __future__ import annotations

from examples.recipes.checkout.domain import Order
from examples.recipes.checkout.order_service import UNIT_PRICE_CENTS
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService


class OrderServiceWithoutRelease:
    """Two recipe pages need this code to RUN, not to be described: ``help-me-debug-and-fix-this-
    bug`` (the bug, before its fix) and ``review-a-refactoring-did-behaviour-change`` (the
    refactoring that drops the release call while every test stays green). It is kept beside
    ``OrderService`` rather than reconstructed by a flag, so each page embeds real source and each
    run is a real run.

    Never the implementation to copy: ``OrderService`` is. A trace names the class it was told to
    name, and both are wrapped as ``OrderService``
    (``trace_object(..., class_name="OrderService")``) -- which is exactly what makes one approved
    trace comparable across the two.
    """

    def __init__(
        self, inventory: InventoryService, payments: PaymentService, orders: OrderRepository
    ) -> None:
        self._inventory = inventory
        self._payments = payments
        self._orders = orders

    def place_order(self, customer_id: str, sku: str, quantity: int, card_number: str) -> str:
        self._inventory.reserve(sku, quantity)
        amount_cents = UNIT_PRICE_CENTS * quantity
        self._payments.charge(customer_id, amount_cents, card_number)
        order_id = f"ORD-{customer_id}-{sku}-{quantity}"
        self._orders.save(Order(order_id, customer_id, sku, quantity, amount_cents))
        return order_id
```

## A saída real

A narrativa da própria execução que falhou, em
`narrative-traces/traces/declined_payment_fixture/test_the_stock_is_released_when_the_card_is_declined_before_the_fix.md`
(a primeira asserção que falha é `assert 3 == 5` — três unidades restantes de
cinco — e a narrativa explica por quê):

```text
---
type: trace
run: neat ram melts
scenario: Test the stock is released when the card is declined before the fix
entry_point: OrderService.place_order
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 3
error_count: 2
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test the stock is released when the card is declined before the fix
**Duration:** 0ms | **Result:** FAILED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) #1.2

    > ❌ `PaymentDeclinedError`: card declined by the issuer — 0ms
  - ❌ `PaymentDeclinedError`: card declined by the issuer
```

A correção é um único `except`: liberar o que foi reservado e deixar a recusa
se propagar como antes.

```python
"""The checkout: reserve the stock, charge the card, save the order -- and release on a decline."""

from __future__ import annotations

from examples.recipes.checkout.domain import Order, PaymentDeclinedError
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService

UNIT_PRICE_CENTS = 3999


class OrderService:
    def __init__(
        self, inventory: InventoryService, payments: PaymentService, orders: OrderRepository
    ) -> None:
        self._inventory = inventory
        self._payments = payments
        self._orders = orders

    def place_order(self, customer_id: str, sku: str, quantity: int, card_number: str) -> str:
        self._inventory.reserve(sku, quantity)
        amount_cents = UNIT_PRICE_CENTS * quantity
        try:
            self._payments.charge(customer_id, amount_cents, card_number)
        except PaymentDeclinedError:
            self._inventory.release(sku, quantity)
            raise
        order_id = f"ORD-{customer_id}-{sku}-{quantity}"
        self._orders.save(Order(order_id, customer_id, sku, quantity, amount_cents))
        return order_id
```

A mesma reprodução, agora passando, contra o checkout corrigido:

```text
---
type: trace
run: neat ram melts
scenario: Test the stock is released when the card is declined
entry_point: OrderService.place_order
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 4
error_count: 2
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test the stock is released when the card is declined
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) #1.2

    > ❌ `PaymentDeclinedError`: card declined by the issuer — 0ms
  - **InventoryService.release**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.3
  - ❌ `PaymentDeclinedError`: card declined by the issuer
```

Com o modo de aprovação ligado, a primeira execução do teste corrigido grava a
estrutura sem valores ao lado dos traces aprovados, como um `.received.nt`, e
falha; `uv run poe approve` (o console script `narrativetrace-approve`) a promove
ao trace aprovado commitado, que passa a ser a forma deste fluxo:

```text
scenario: Test the stock is released when the card is declined

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
  #1.3 - InventoryService.release(sku, quantity) → value
```

## Como ler

No trace que falhou:

- `#1 OrderService.place_order` termina com `❌ PaymentDeclinedError` e sem
  valor de retorno: a chamada que o cliente fez não foi concluída.
- `#1.1 InventoryService.reserve(sku: "SKU-KB", quantity: 2)` não tem `❌` — foi
  concluída, e `→ null` é apenas o Python dizendo que retornou `None`. Duas
  unidades estão agora retidas.
- `#1.2 PaymentService.charge` lançou uma exceção. Seus parâmetros dizem o que
  foi tentado: `amount_cents: 7998` pelas duas unidades, `card: [REDACTED]`.
- **Nada vem depois de `#1.2`.** `#1` vai direto da cobrança para a sua própria
  falha, então as duas unidades que `#1.1` reservou continuam retidas. Essa
  ausência é o bug, e a mensagem da exceção nunca a menciona — o trace é o que
  torna uma omissão visível, porque mostra o fluxo inteiro e não apenas a linha
  que lançou a exceção.

No trace que passa: `#1.3 InventoryService.release(sku: "SKU-KB", quantity: 2)`
agora fica entre a cobrança e a falha. `#1` ainda termina na recusa — isso está
correto, o cartão do cliente realmente foi recusado — e o estoque voltou.

No trace aprovado: as mesmas quatro chamadas com os *nomes* dos parâmetros e
nenhum valor, e por isso ele pode ser commitado e lido em uma revisão. `→ value`
em `reserve` e `release` diz que elas retornaram algo — o `None` do Python conta,
já que não existe `void` — sem dizer o quê. `#1.3` agora faz parte da forma
fixada: uma mudança posterior que remova a liberação faz um teste que passa
falhar com um diff nomeando `InventoryService.release`, de modo que este bug não
pode voltar silenciosamente. Isso é
[Revise uma refatoração: o comportamento mudou](revise-uma-refatoracao-o-comportamento-mudou.md).

## O que não é capturado

- **O trace mostra as chamadas que aconteceram, não as que deveriam ter
  acontecido.** O `release` ausente é uma ausência que o leitor infere do fluxo;
  nada no artefato diz "falta uma chamada". O que o trace aprovado acrescenta é
  a comparação que transforma uma ausência em uma falha de build — uma vez.
- **Uma exceção engolida dentro de código não envolvido é invisível.** Só os
  objetos envolvidos aparecem. Um `try`/`except` dentro de `OrderService` que
  engolisse a recusa e retornasse normalmente apareceria como uma chamada
  concluída.
- **O número do cartão não pode ser recuperado** a partir do trace nem do log.
  Ele é ocultado na captura, aqui pelo valor — o parâmetro se chama `card`, então
  a deny-list de nomes nunca o viu, e o número é válido pelo Luhn.
- **Os tempos não são evidência de um problema de desempenho** em um teste tão
  pequeno: são milissegundos inteiros, e a maioria dessas chamadas arredonda para
  `0`.

**A skill para isto:** `narrativetrace-debug` — ela reproduz o sintoma com a
menor entrada possível, nomeia o span em que o valor ou a chamada diverge, corrige
ali e fixa o fluxo como um teste de regressão com a sua aprovação.
