<!-- source: documentation/recipes/add-logging-to-this-service.md blob 31919267f2b6 | translated: 2026-10-11 | reviewed: - -->

# Adicione logs a este serviço

## O problema

> Adicione logs a este serviço.

O serviço é um checkout. Ele reserva estoque, cobra um cartão e salva um
pedido, e não contém nenhuma instrução de log:

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

O que você realmente quer é aquilo para o qual o logging é um meio: o que esta
chamada fez, com os valores com que fez, no log que sua equipe já lê. Por isso
a resposta abaixo também não escreve nenhuma instrução de log.

## Configuração mínima

Além da [instalação](guia-de-instalacao.md) — `narrativetrace` para o
wrapper e a ponte com o `logging`, `narrativetrace-pytest` para o teste em que
esta página roda —, esta página precisa de um trecho de configuração comum do
`logging`, do tipo que um app real já tem (`handler` abaixo é o handler que ele
já configura, seja qual for). A única linha do NarrativeTrace nele é o filtro
que torna `traceName` disponível para o formato:

```python
handler.addFilter(NarrativeContextFilter())  # torna traceName disponível para o formato abaixo
logging.basicConfig(
    level=logging.DEBUG,  # a ponte registra toda chamada em DEBUG; INFO esconderia tudo
    format="%(levelname)-5s [%(traceName)s] [%(name)s] - %(message)s",
    handlers=[handler],
)
```

`NarrativeContextFilter` carimba o próprio nome do trace em cada registro, e o
formato o lê. O nível é `DEBUG` porque a ponte registra toda chamada em
`DEBUG` — o `logging` do Python não tem `TRACE`. Para onde os registros vão é
decisão do handler, não do NarrativeTrace.

## O cenário

Cada colaborador é envolvido uma única vez, onde é construído — o próprio
checkout por último, para que as chamadas feitas através dele sejam capturadas
antes de chegarem à implementação real. Depois da chamada, `export_to_logger`
reproduz o trace capturado pelo logger configurado acima. Nada mais muda:

```python
"""documentation/recipes/add-logging-to-this-service.md's scenario: the checkout, with no log
statement anywhere in it, logs every call through the project's own ``logging`` setup once its
collaborators are wrapped.

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs it in its own pytest process so the
log file the page embeds holds this scenario alone.
"""

from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, export_to_logger, trace_object

# A fixed trace id, adopted so this page's embedded output names the same trace every run -- the
# mechanism a boundary uses for an inbound trace header. A real run generates a random id.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_a_customer_checks_out(narrative_trace: ContextVarNarrativeContext) -> None:
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

O cenário é um teste pytest porque é onde um fluxo como este já costuma ser
exercitado (este repositório o roda como um módulo de fixture em um processo
pytest próprio, de modo que o log abaixo contém só este cenário — daí os
imports `examples.…` e o nome do módulo); a mesma configuração funciona em um
script, em um handler `FastAPI` ou em um worker. A fixture `narrative_trace` é
o que grava os artefatos de trace por teste que as outras receitas leem.

## A saída real

O log que a execução acima gravou, pelo logger do próprio projeto:

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

## Como ler

- `→` abre uma chamada, `←` fecha a aberta mais recentemente, de modo que a
  indentação é desnecessária: o primeiro `→ OrderService.place_order` e o último
  `← returned: "ORD-C-1234-SKU-KB-2"` são a mesma chamada, e tudo o que está
  entre eles aconteceu dentro dela. Nos artefatos de trace, as mesmas quatro
  chamadas carregam os ids de span `#1`, `#1.1`, `#1.2` e `#1.3` —
  [Revise um fluxo complexo antes de alterá-lo](revise-um-fluxo-complexo-antes-de-altera-lo.md)
  as lê dessa forma.
- Cada linha traz os *nomes* de parâmetro que o método declara, e é isso que a
  torna uma frase em vez de uma tupla: `reserve(sku: "SKU-KB", quantity: 2)`
  dispensa legenda. Um argumento dataclass é renderizado campo a campo —
  `Order(order_id="ORD-C-1234-SKU-KB-2", …)`.
- `← returned: null` é um método que retornou `None` — Python não tem `void`,
  então um método que não retorna nada ainda assim retorna algo, e o log diz
  isso. `← returned: "PAY-C-1234-7998"` carrega o valor: `charge` devolvendo o
  id do próprio gateway, e `amount_cents: 7998` é de onde vem o preço de dois
  teclados.
- Dois valores sumiram. `card_number: [REDACTED]` foi ocultado pelo seu *nome* —
  a deny-list sempre ativa, sem decorador, sem configuração. `card: [REDACTED]`,
  uma linha abaixo, foi ocultado pelo seu *valor*: o parâmetro se chama `card`,
  que a deny-list não conhece, e o número que ele continha é válido pelo Luhn,
  então a regra de formato de valor o pegou do mesmo jeito. Veja
  [Privacidade e ocultação](privacidade-e-ocultacao.md).
- `[solid wand romps]` é o nome do próprio trace, de modo que todas as linhas
  de um checkout podem ser extraídas com grep de um log movimentado.

A conclusão que isso sustenta: a narrativa veio dos nomes dos métodos, dos
nomes dos parâmetros e dos valores, e nenhuma instrução de log foi escrita
para obtê-la.

## O que não é capturado

- **Só o código envolvido é registrado.** Quatro objetos foram envolvidos acima,
  então aparecem quatro chamadas. Uma chamada entre dois objetos não envolvidos
  — ou um método privado dentro de `OrderService` — fica invisível aqui. Se
  envolver cada colaborador à mão não é o que você quer, os decoradores e o
  middleware ASGI se encaixam sem tocar no código de construção:
  [Escolhendo uma integração](escolhendo-uma-integracao.md).
- **Um valor que case com as regras de ocultação é substituído antes de ser
  gravado,** inclusive nesta linha de log. Isso não é configurável para baixo, e
  significa que um parâmetro ocultado não pode ser recuperado a partir do log.
- **O nível do próprio logger continua valendo.** Estes registros são `DEBUG`;
  com o handler em `INFO` o log fica vazio e nada avisa você.
- **As linhas são gravadas quando `export_to_logger` roda,** depois que a
  chamada retornou ou lançou uma exceção, então um processo que morre no meio de
  uma chamada não registra nada dela. Para linhas conforme as chamadas
  acontecem, anexe o consumidor ao vivo: [Guia de logging](guia-de-logging.md).
- **Os tempos não estão nas linhas de log.** A duração de cada chamada está nos
  artefatos de trace, não aqui.

**A skill para isto:** `add-narrative-tracing` — ela instala os pacotes, envolve
a primeira classe e confere a configuração com o `narrativetrace-doctor`.
