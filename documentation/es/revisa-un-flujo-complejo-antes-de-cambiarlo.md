<!-- source: documentation/recipes/review-a-complex-flow-before-changing-it.md blob fb581f90f1a3 | translated: 2026-10-11 | reviewed: - -->

# Revisa un flujo complejo antes de cambiarlo

## El problema

> Antes de cambiar el checkout, dime qué hace en realidad.

Leer el código fuente responde qué *puede* hacer. Una ejecución responde qué
*hace* con estas entradas — en qué orden, con qué valores, y dónde el flujo
sale del código que estás a punto de editar. Esta página deliberadamente nunca
muestra la implementación: ese es el sentido de leer una ejecución.

## Configuración mínima

Nada más allá de la [instalación](guia-de-instalacion.md) para los dos
artefactos de traza. Las líneas de log necesitan una pieza de configuración
ordinaria de `logging`, exactamente como en
[Añade logging a este servicio](anade-registro-a-este-servicio.md). El nivel de
captura es un solo ajuste, y `SUMMARY` es el que usa esta página junto al
`DETAIL` por defecto:

```bash
NARRATIVETRACE_LEVEL=SUMMARY uv run pytest   # OFF | ERRORS | SUMMARY | NARRATIVE | DETAIL
```

Consulta [Guía de configuración, nivel de tracing](guia-de-configuracion.md).

## El escenario

Una ejecución representativa del flujo — una prueba existente es la más barata
de tomar prestada, y esta es esa prueba:

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

## La salida real

**En `DETAIL`** (el valor por defecto), `narrative-traces/traces/checkout_review_fixture/test_a_customer_buys_two_keyboards.md`:

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

**En `SUMMARY`**, la misma ejecución de la misma prueba:

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

**El log que escribió el mismo flujo** a través del logger propio del
proyecto, con valores y todo:

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

**La traza estructural de esa ejecución**, `narrative-traces/structural/checkout_review_fixture/test_a_customer_buys_two_keyboards.nt`:

```text
scenario: Test a customer buys two keyboards

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) → value
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) → value
  #1.3 - OrderRepository.save(order) → value
```

## Cómo leerlo

**El flujo, desde el artefacto `DETAIL`.** `#1` es la llamada que hizo la
prueba y la única raíz: todo lo que está indentado bajo ella ocurrió dentro de
ella, en el orden impreso. `#1.1` reserva dos unidades antes de cobrar nada;
`#1.2` cobra 7998 — dos unidades a 3999, así que el precio se deriva de la
cantidad y no se pasa como argumento; `#1.3` guarda un pedido que ya lleva el
id que devuelve `#1`. Leído como una frase: este checkout reserva primero,
cobra segundo, guarda tercero, y el id del pedido se genera antes del
guardado. Un cambio que cobre antes de reservar, o guarde antes de cobrar, es
un cambio a *esto*, y ahora lo sabes sin fiarte de un comentario.

**Para qué sirve cada nivel.** `DETAIL` lleva los valores de los parámetros, y
es lo que lees mientras trabajas en el flujo. En `SUMMARY` cada valor de
parámetro está vacío — los acentos graves no contienen nada — porque se
suprimió en la captura, no se ocultó al renderizar, y solo se conservan las
raíces y las llamadas hoja; este flujo tiene dos niveles de profundidad, así
que ningún frame es intermedio y aparecen las mismas cuatro llamadas. Un flujo
más profundo pierde su parte media. Los valores de retorno sobreviven en cada
nivel activo: el retorno es la carga útil de una narrativa. Usa `SUMMARY`
donde la forma y los resultados son lo que necesitas y los valores son un
coste — una ejecución de CI, una prueba de resistencia larga — y `OFF`/`ERRORS`
en producción hasta que necesites más.

**Qué salida lee una persona y cuál un agente.** Las líneas de log son para la
persona de guardia: se intercalan con todo lo demás que registra el servicio,
llevan los valores, y llevan como clave el nombre de la traza —
`[solid wand romps]` — de modo que un checkout se puede extraer con grep de un
archivo muy cargado. El `.nt` es para el agente y el revisor: **sin valores
por construcción** — compáralo con la línea de log de arriba y la diferencia
no es que los valores se reemplazaron sino que nunca se escribieron.
`(customer_id, sku, quantity, card_number)` son los *nombres* de los
parámetros; `→ value` dice que se devolvió un valor sin decir cuál (en
`reserve` y `save` es el `None` de Python, que igualmente cuenta — no hay
`void`). Eso es lo que lo hace seguro para commitear, para comparar en una
revisión y para entregar a un modelo: no puede filtrar un id de cliente, y no
cambia cuando cambian los datos — solo cuando cambian las *llamadas*. Fijarlo
es [Revisa una refactorización: ¿cambió el comportamiento?](revisa-una-refactorizacion-cambio-el-comportamiento.md).

## Qué no se captura

- **Las llamadas dentro de objetos sin envolver.** Se envolvieron cuatro
  objetos; una llamada entre dos objetos que están detrás de ellos, o un
  método privado, nunca aparece. Un flujo que parece superficial puede ser
  profundo.
- **Lo que la integración elegida no intercepta.** `trace_object` solo ve las
  llamadas hechas *a través* del wrapper: una llamada interna que un objeto se
  hace a sí mismo (`self._helper()`) le es invisible, mientras que un
  decorador sobre ese método sí la vería.
  [Eligiendo una integración](eligiendo-una-integracion.md) es el balance por
  camino, y esta es la parte que cambia lo que puedes leer aquí.
- **El trabajo que salió del thread.** Una llamada entregada a un executor sin
  el contexto no viaja más lejos; la traza termina donde terminó el thread.
- **Los valores que atrapó la lista de denegación o la regla de forma del
  valor**, aquí `card_number` y `card`, son `[REDACTED]` tanto en el log como
  en el artefacto `DETAIL`, y están ausentes por construcción del `.nt`.
- **Una ejecución, no el contrato.** Otra entrada toma otro camino — un sku
  agotado nunca llega a `#1.2`.

**La skill para esto:** `narrativetrace-verify` — escribe primero la
intención, ejecuta el camino real más pequeño y lee la traza sin valores
contra esa intención antes de dar nada por terminado.
