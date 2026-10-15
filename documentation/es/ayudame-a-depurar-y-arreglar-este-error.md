<!-- source: documentation/recipes/help-me-debug-and-fix-this-bug.md blob a176672c9aac | translated: 2026-10-11 | reviewed: - -->

# Ayúdame a depurar y arreglar este error

## El problema

> Ayúdame a depurar y arreglar este error: a un cliente le rechazaron la
> tarjeta y el teclado nunca volvió al stock.

El error que tiene el equipo es `PaymentDeclinedError: card declined by the issuer`,
que no es el error. El error es lo que hizo el checkout *después*.

## Configuración mínima

Nada más allá de la [instalación](guia-de-instalacion.md): el fixture
`narrative_trace` de [`narrativetrace-pytest`](guia-de-pytest.md) escribe una
traza por prueba sin configuración. El último paso de esta página — fijar el
flujo arreglado — activa el modo de aprobación, que es un único ajuste:

```bash
NARRATIVETRACE_APPROVAL=true uv run pytest   # compara la estructura de cada prueba que pasa con su traza aprobada commiteada
```

Consulta [Guía de configuración, artefacto estructural y modo de aprobación](guia-de-configuracion.md)
y [Qué commitear](que-commitear.md).

## El escenario

Reprodúcelo en la prueba más pequeña que pueda fallar por esta razón — una
tarjeta rechazada debe dejar el stock como lo encontró:

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

La segunda prueba ejecuta la misma reproducción contra el checkout tal como
estaba antes del arreglo, que es la ejecución de la que sale la primera traza
de abajo. (Este repositorio guarda ambas en un módulo fixture que ejecuta un
proceso de pytest propio, porque la segunda prueba falla por diseño; en tu
proyecto la prueba que falla es simplemente tu prueba.)

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

## La salida real

La narrativa propia de la ejecución fallida, en
`narrative-traces/traces/declined_payment_fixture/test_the_stock_is_released_when_the_card_is_declined_before_the_fix.md`
(la primera aserción que falla es `assert 3 == 5` — tres unidades de cinco — y
la narrativa explica por qué):

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

El arreglo es un solo `except`: liberar lo que se reservó y luego dejar que el
rechazo se propague como antes.

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

La misma reproducción, ahora pasando, contra el checkout arreglado:

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

Con el modo de aprobación activado, la primera ejecución de la prueba
arreglada escribe su estructura sin valores junto a las trazas aprobadas como
un `.received.nt` y falla; `uv run poe approve` (el script de consola
`narrativetrace-approve`) lo promueve a la traza aprobada commiteada, que
pasa a ser la forma de este flujo:

```text
scenario: Test the stock is released when the card is declined

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
  #1.3 - InventoryService.release(sku, quantity) → value
```

## Cómo leerlo

En la traza que falla:

- `#1 OrderService.place_order` termina con `❌ PaymentDeclinedError` y sin
  valor de retorno: la llamada que hizo el cliente no se completó.
- `#1.1 InventoryService.reserve(sku: "SKU-KB", quantity: 2)` no tiene `❌` —
  se completó, y `→ null` es solo Python diciendo que devolvió `None`. Ahora
  hay dos unidades retenidas.
- `#1.2 PaymentService.charge` lanzó una excepción. Sus parámetros dicen qué se
  intentó: `amount_cents: 7998` por las dos unidades, `card: [REDACTED]`.
- **Nada sigue a `#1.2`.** `#1` pasa directamente del cobro a su propio fallo,
  así que las dos unidades que reservó `#1.1` siguen retenidas. Esa ausencia
  es el error, y el mensaje de la excepción nunca la menciona — la traza es lo
  que hace visible una omisión, porque muestra el flujo entero y no solo la
  línea que lanzó.

En la traza que pasa: `#1.3 InventoryService.release(sku: "SKU-KB", quantity: 2)`
ahora está entre el cobro y el fallo. `#1` sigue terminando en el rechazo —
eso es correcto, la tarjeta del cliente de verdad fue rechazada — y el stock
ha vuelto.

En la traza aprobada: las mismas cuatro llamadas con los *nombres* de sus
parámetros y ningún valor, que es la razón por la que se puede commitear y
leer en una revisión. `→ value` en `reserve` y `release` dice que devolvieron
algo — el `None` de Python cuenta, al no haber `void` — sin decir qué. `#1.3`
ahora forma parte de la forma fijada: un cambio posterior que elimine el
release hace fallar una prueba que pasa con un diff que nombra
`InventoryService.release`, de modo que este error no puede volver en
silencio. Eso es
[Revisa una refactorización: ¿cambió el comportamiento?](revisa-una-refactorizacion-cambio-el-comportamiento.md).

## Qué no se captura

- **La traza muestra las llamadas que ocurrieron, no las que debieron
  ocurrir.** El `release` que falta es una ausencia que el lector infiere del
  flujo; nada en el artefacto dice "falta una llamada". Lo que añade la traza
  aprobada es la comparación que convierte una ausencia en un fallo de build
  — una vez.
- **Una excepción tragada dentro de código sin envolver es invisible.** Solo
  aparecen los objetos envueltos. Un `try`/`except` dentro de `OrderService`
  que se comiera el rechazo y devolviera con normalidad se vería como una
  llamada completada.
- **El número de tarjeta no se puede recuperar** de la traza ni del log. Se
  oculta en la captura, aquí por valor — el parámetro se llama `card`, así que
  la lista de denegación por nombre nunca lo vio, y el número es válido según
  Luhn.
- **Los tiempos no son evidencia de un problema de rendimiento** en una prueba
  tan pequeña: son milisegundos enteros, y la mayoría de estas llamadas se
  redondean a `0`.

**La skill para esto:** `narrativetrace-debug` — reproduce el síntoma con la
entrada más pequeña, nombra el span donde el valor o la llamada diverge, lo
arregla ahí y fija el flujo como prueba de regresión con tu aprobación.
