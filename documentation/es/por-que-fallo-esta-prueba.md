<!-- source: documentation/recipes/why-did-this-test-fail.md blob 2d305deb9ab7 | translated: 2026-10-11 | reviewed: - -->

# Por qué falló esta prueba

## El problema

> ¿Por qué falló esta prueba?

Una prueba del checkout está en rojo. La aserción dice qué no coincidió; no
dice qué hizo el código por el camino, que es la parte que necesitas para saber
si lo equivocado es el código o la expectativa.

## Configuración mínima

Nada más allá de la [instalación](guia-de-instalacion.md). El fixture
`narrative_trace` de [`narrativetrace-pytest`](guia-de-pytest.md) escribe una
narrativa por prueba sin configuración — también para una prueba que falla,
que es el caso de esta página. Los archivos quedan en
`narrative-traces/traces/<module>/<test>.md`, y
`narrative-traces/manifest.json` lista cada artefacto de cada escenario cuando
conoces el nombre de la prueba pero no el de su archivo.

## El escenario

La prueba que falla:

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

## La salida real

Lo que reportó el runner:

```text
assert 'ORD-C-1234-SKU-KB-2' == 'ORD-C-1234-SKU-KB-1'
  
  - ORD-C-1234-SKU-KB-1
  ?                   ^
  + ORD-C-1234-SKU-KB-2
  ?                   ^
```

Y lo que escribió la misma ejecución a su lado, en
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

## Cómo leerlo

Lee la narrativa de arriba abajo contra la aserción, un span a la vez:

- `#1 OrderService.place_order(... quantity: 2 ...) → "ORD-C-1234-SKU-KB-2"`.
  El valor que rechazó la aserción está ahí mismo, y también la entrada que lo
  produjo: la llamada pidió **dos** teclados.
- `#1.1 InventoryService.reserve(sku: "SKU-KB", quantity: 2)` — dos unidades
  reservadas, coherente con la llamada.
- `#1.2 PaymentService.charge(..., amount_cents: 7998, ...)` — 7998 son dos
  unidades a 3999, así que el precio también concuerda con la cantidad.
- `#1.3 OrderRepository.save(order: Order(... quantity=2 ...))` — lo que se
  guardó concuerda con lo que se pidió.
- `**Result:** FAILED` en la cabecera es el veredicto de la *prueba*, no del
  código: `error_count: 0` y todos los spans se completaron. Nada lanzó una
  excepción.

Cada span concuerda con todos los demás y con la llamada que los inició. La
expectativa — `ORD-C-1234-SKU-KB-1` — es lo único de la ejecución que habla de
un teclado, así que es lo que está desactualizado; el fixture contra el que se
escribió ha cambiado desde entonces para pedir dos. El arreglo está en la
prueba.

La lectura opuesta es la otra receta: cuando un span *discrepa* de la
intención — una cantidad que cambia entre dos llamadas, una llamada que debía
seguir y no lo hizo — el código es el equivocado, y
[Ayúdame a depurar y arreglar este error](ayudame-a-depurar-y-arreglar-este-error.md)
es ese recorrido.

## Qué no se captura

- **Solo la ejecución de esa prueba.** La narrativa se escribe por prueba, por
  ejecución. Un fallo que ocurre una de cada veinte ejecuciones necesita que
  una de esas ejecuciones sea la que escribió el archivo; cada ejecución
  sobrescribe el archivo de la anterior, y una ejecución que falla no hace
  avanzar en absoluto el baseline `.nt` sin valores.
- **La aserción no está en la traza.** Las dos salidas de arriba vienen de dos
  lugares — el runner reportó la discrepancia, el plugin escribió el flujo — y
  nada las correlaciona automáticamente más allá del nombre del escenario.
- **Un valor que una prueba calculó pero nunca pasó a una llamada trazada es
  invisible.** La traza lleva los parámetros y valores de retorno de las
  llamadas envueltas, no las variables locales.
- **Los tiempos en una ejecución fallida no significan nada.** La ejecución
  dejó de ser representativa en el momento en que la aserción lanzó.

**La skill para esto:** `narrativetrace-debug` — parte del síntoma, lee el
primer span donde un valor diverge y lo nombra por su span id.
