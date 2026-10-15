<!-- source: documentation/recipes/review-a-refactoring-did-behaviour-change.md blob ccf6f5a8e09a | translated: 2026-10-11 | reviewed: - -->

# Revisa una refactorización: ¿cambió el comportamiento?

## El problema

> Refactoricé el checkout. Las pruebas están en verde. ¿Cambió el comportamiento?

Verde significa que ninguna aserción lo notó. Una refactorización que elimina
una llamada sobre la que nadie hace aserciones está en verde y mal, y esta es
la forma más común: la llamada compensatoria en un camino de error, a la que
no llega ninguna prueba del camino feliz.

## Configuración mínima

Además de la [instalación](guia-de-instalacion.md), el modo de aprobación — un
solo ajuste, y un directorio de trazas aprobadas commiteadas:

```bash
NARRATIVETRACE_APPROVAL=true uv run pytest   # compara, no solo escribe; NARRATIVETRACE_APPROVED_DIR por defecto es test-narratives
```

La primera ejecución de cada prueba escribe
`test-narratives/<module>/<test>.received.nt` y falla; lo lees, ejecutas
`uv run poe approve` (el script de consola `narrativetrace-approve`) para
promover cada traza recibida revisada a un `.approved.nt`, y los commiteas.
Consulta [Guía de configuración, artefacto estructural y modo de aprobación](guia-de-configuracion.md)
y [Qué commitear](que-commitear.md).

## El escenario

La prueba fija el camino de error que una refactorización tiene más
probabilidad de romper — una tarjeta rechazada no debe guardar ningún pedido —
y pasa contra ambas versiones del checkout, que es todo el problema:

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

## La salida real

La traza aprobada commiteada, en
`test-narratives/refactored_checkout_fixture/test_a_declined_card_saves_no_order.approved.nt`:

```text
scenario: Test a declined card saves no order

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
  #1.3 - InventoryService.release(sku, quantity) → value
```

El veredicto de la ejecución refactorizada — las aserciones propias de la
prueba pasaron, la estructura no, así que pytest reporta un error en el
teardown de la prueba:

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

Y la traza recibida que ofrece para su revisión, que `uv run poe approve`
promovería:

```text
scenario: Test a declined card saves no order

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
```

(La ruta en `Received:` es la de este mismo repositorio: la ejecución que
produce esta página apunta `NARRATIVETRACE_APPROVED_DIR` bajo `build/`, porque
el paso que escribe una página no puede escribir en el árbol de código fuente.
En tu proyecto es `test-narratives`, junto a la traza aprobada.)

## Cómo leerlo

- **La primera línea nombra el cambio, no solo el hecho de que lo hay:**
  `-1 call InventoryService.release`. Una llamada menos, y cuál.
- **El cuerpo del diff es la forma fijada con la línea eliminada marcada.**
  `#1`, `#1.1` y `#1.2` no han cambiado y no están marcados;
  `-  #1.3 - InventoryService.release(sku, quantity) → value` es el
  comportamiento que se fue. Un revisor que nunca ha visto este código puede
  saber qué hizo la refactorización a partir de unas pocas líneas.
- **Las aserciones propias de la prueba pasaron.** El fallo es el de la
  aprobación, y ese es el sentido: la suite afirma que no se guarda ningún
  pedido, y la refactorización no rompió eso. Nada en la prueba miró jamás el
  release, y no tenía por qué.
- **Ahora decide.** Si eliminar el release es intencionado — el llamador lo
  asumió, por ejemplo — ejecuta `uv run poe approve`, revisa el diff en el
  archivo promovido y commitéalo: la nueva forma pasa a ser la fijada. Si no es
  intencionado, acabas de atrapar el error que
  [Ayúdame a depurar y arreglar este error](ayudame-a-depurar-y-arreglar-este-error.md)
  arregló, volviendo a entrar. En ambos casos la decisión queda registrada en
  el repositorio, por una persona, en un archivo que un revisor puede leer.
- **La traza aprobada no tiene valores**, así que aprobarla no filtra nada y un
  cambio en los datos de prueba nunca la hace fallar: `(customer_id, sku,
  quantity, card_number)` son nombres, `!! PaymentDeclinedError` es un
  resultado.

Esta es la idea del approval testing (probar contra un resultado aprobado),
aplicada a las trazas: el artefacto commiteado es la forma del comportamiento, no una
instantánea de sus valores.

## Qué no se captura

- **Esto es una comparación estructural: las mismas llamadas, en el mismo
  orden, con los mismos resultados.** No es una prueba de que cada valor sea
  igual. Una refactorización que cobra 7998 donde cobraba 3999, con cada
  llamada en su sitio, pasa esta barrera — para eso están tus aserciones, y el
  artefacto `DETAIL` es donde lo verías.
- **Solo las llamadas que la integración intercepta.** Una llamada privada
  eliminada, o una entre dos objetos sin envolver, es invisible para la traza
  aprobada exactamente igual que para la traza.
- **Una prueba que no se ejecuta no se compara.** La aprobación protege los
  escenarios que fijaste; un flujo sin prueba no tiene traza aprobada, y
  borrar una prueba borra su barrera (el `.approved.nt` queda entonces
  huérfano, lo que `narrativetrace-doctor` reporta).
- **Los tiempos nunca forman parte.** La traza aprobada no lleva duraciones,
  así que no puede atrapar un cambio que solo hizo el flujo más lento.

**La skill para esto:** `narrativetrace-verify` — lee la traza estructural
contra la intención del cambio y fija el flujo como traza aprobada con tu
aprobación.
