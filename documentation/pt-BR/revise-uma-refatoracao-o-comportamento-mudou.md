<!-- source: documentation/recipes/review-a-refactoring-did-behaviour-change.md blob ccf6f5a8e09a | translated: 2026-10-11 | reviewed: - -->

# Revise uma refatoração: o comportamento mudou

## O problema

> Refatorei o checkout. Os testes estão verdes. O comportamento mudou?

Verde significa que nenhuma asserção percebeu. Uma refatoração que remove uma
chamada em que ninguém faz asserção fica verde e errada, e essa é a forma comum
do problema: a chamada compensatória em um caminho de erro, que nenhum teste de
caminho feliz alcança.

## Configuração mínima

Além da [instalação](guia-de-instalacao.md), o modo de aprovação — uma única
configuração e um diretório de traces aprovados commitados:

```bash
NARRATIVETRACE_APPROVAL=true uv run pytest   # compara, em vez de apenas gravar; NARRATIVETRACE_APPROVED_DIR tem como padrão test-narratives
```

A primeira execução de cada teste grava
`test-narratives/<module>/<test>.received.nt` e falha; você o lê, roda
`uv run poe approve` (o console script `narrativetrace-approve`) para promover
cada trace recebido revisado a um `.approved.nt`, e commita esses arquivos. Veja
[Guia de configuração, artefato estrutural e modo de aprovação](guia-de-configuracao.md)
e [O que commitar](o-que-commitar.md).

## O cenário

O teste fixa o caminho de erro que uma refatoração tem mais chance de quebrar —
um cartão recusado não deve salvar nenhum pedido — e passa contra as duas versões
do checkout, que é todo o problema:

```python
"""The test documentation/recipes/review-a-refactoring-did-behaviour-change.md pins: a declined card
must save no order. It passes before and after the refactoring -- which is the whole point of the
page -- so only the approved structure can object.

A fixture because ``recipe_artifacts.py`` runs it twice under approval mode, once per version of the
checkout, and reads the verdicts. ``NARRATIVETRACE_RECIPE_REFACTORED`` picks the version: in your
project the refactoring is an edit to one file and this switch does not exist.
"""

import os

import pytest

from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.env import REFACTORED_ENV
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.order_service_without_release import OrderServiceWithoutRelease
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, trace_object

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_a_declined_card_saves_no_order(narrative_trace: ContextVarNarrativeContext) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    service_class = OrderServiceWithoutRelease if os.environ.get(REFACTORED_ENV) else OrderService
    checkout = trace_object(
        service_class(inventory, payments, orders), narrative_trace, class_name="OrderService"
    )

    with pytest.raises(PaymentDeclinedError):
        checkout.place_order("C-1234", "SKU-KB", 2, PaymentService.DECLINING_CARD)

    assert repository.saved() == []
```

## A saída real

O trace aprovado commitado, em
`test-narratives/refactored_checkout_fixture/test_a_declined_card_saves_no_order.approved.nt`:

```text
scenario: Test a declined card saves no order

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
  #1.3 - InventoryService.release(sku, quantity) → value
```

O veredito da execução refatorada — as asserções do próprio teste passaram, a
estrutura não, então o pytest reporta um erro no teardown do teste:

```text
Structure changed against the approved trace (-1 call InventoryService.release):
 scenario: Test a declined card saves no order
 
 #1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
   #1.1 - InventoryService.reserve(sku, quantity) → value
   #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
-  #1.3 - InventoryService.release(sku, quantity) → value
Received: examples/recipes/checkout/build/review-a-refactoring-did-behaviour-change/approved-after-the-refactoring/refactored_checkout_fixture/test_a_declined_card_saves_no_order.received.nt
If this change is intended, approve it (run `uv run poe approve` or `narrativetrace-approve`). → narrativetrace-doctor skill
```

E o trace recebido que ele oferece para revisão, que `uv run poe approve`
promoveria:

```text
scenario: Test a declined card saves no order

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
```

(O caminho em `Received:` é o deste repositório: a execução que produz esta
página aponta `NARRATIVETRACE_APPROVED_DIR` para dentro de `build/`, porque o
passo que escreve uma página não pode escrever na árvore de código-fonte. No seu
projeto é `test-narratives`, ao lado do trace aprovado.)

## Como ler

- **A primeira linha nomeia a mudança, não apenas o fato dela:**
  `-1 call InventoryService.release`. Uma chamada a menos, e qual.
- **O corpo do diff é a forma fixada com a linha removida marcada.** `#1`,
  `#1.1` e `#1.2` não mudaram e não estão marcados;
  `-  #1.3 - InventoryService.release(sku, quantity) → value` é o comportamento
  que saiu. Um revisor que nunca viu este código consegue dizer o que a
  refatoração fez a partir de poucas linhas.
- **As asserções do próprio teste passaram.** A falha é a da aprovação, e esse é
  o ponto: a suíte afirma que nenhum pedido é salvo, e a refatoração não quebrou
  isso. Nada no teste jamais olhou para a liberação, e nada precisava olhar.
- **Agora decida.** Se remover a liberação é intencional — o chamador assumiu essa
  tarefa, digamos —, rode `uv run poe approve`, revise o diff no arquivo
  promovido e commite: a nova forma passa a ser a fixada. Se não é intencional,
  você acabou de pegar o bug que
  [Ajude-me a depurar e corrigir este bug](ajude-me-a-depurar-e-corrigir-este-bug.md)
  corrigiu, voltando. De um jeito ou de outro, a decisão fica registrada no
  repositório, por um humano, em um arquivo que um revisor pode ler.
- **O trace aprovado não tem valores**, então aprová-lo não vaza nada e uma
  mudança nos dados de teste nunca o faz falhar: `(customer_id, sku, quantity,
  card_number)` são nomes, `!! PaymentDeclinedError` é um resultado.

Esta é a ideia do approval testing, aplicada a traces — os traces de
aprovação: o artefato commitado é a forma do comportamento, não um
snapshot de seus valores.

## O que não é capturado

- **Esta é uma comparação estrutural: as mesmas chamadas, na mesma ordem, com os
  mesmos resultados.** Não é uma prova de que todo valor é igual. Uma refatoração
  que cobre 7998 onde cobrava 3999, com todas as chamadas no lugar, passa por
  este gate — é para isso que servem as suas asserções, e o artefato `DETAIL` é
  onde você veria.
- **Só as chamadas que a integração intercepta.** Uma chamada privada removida,
  ou uma entre dois objetos não envolvidos, é invisível ao trace aprovado
  exatamente como é ao trace.
- **Um teste que não roda não é comparado.** A aprovação protege os cenários que
  você fixou; um fluxo sem teste não tem trace aprovado, e apagar um teste apaga
  o seu gate (o `.approved.nt` passa a ser um órfão, que o `narrativetrace-doctor`
  reporta).
- **Os tempos nunca fazem parte dele.** O trace aprovado não carrega durações,
  então não consegue pegar uma mudança que apenas tornou o fluxo mais lento.

**A skill para isto:** `narrativetrace-verify` — ela lê o trace estrutural contra
a intenção da mudança e fixa o fluxo como um trace aprovado com o seu sim.
