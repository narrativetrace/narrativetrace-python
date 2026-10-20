<!-- source: documentation/recipes/trace-in-production-without-the-cost.md blob 36e9d5a351e8 | translated: 2026-10-18 | reviewed: - -->

# Traza en producción sin el coste

## El problema

> Quiero esto en producción para las peticiones que salen mal. No quiero pagar
> una traza completa de cada petición que sale bien.

Eso es un solo ajuste — el nivel de trazado — y esta página es la misma
ejecución vista a través de él dos veces: el checkout con pago rechazado en
`DETAIL`, donde se captura cada valor, y en `ERRORS`, donde solo sobreviven las
ejecuciones que fallaron.

## Configuración mínima

Un nivel, establecido allí donde se configure tu despliegue. Ambos dicen lo
mismo:

```toml
# narrativetrace.toml (or [tool.narrativetrace] in pyproject.toml, never both)
level = "ERRORS"   # "OFF" | "ERRORS" | "SUMMARY" | "NARRATIVE" | "DETAIL"
```

```bash
# or in the environment, which wins over the file
NARRATIVETRACE_LEVEL=ERRORS uv run pytest
```

En código es `ContextVarNarrativeContext(NarrativeTraceConfig(level=TracingLevel.ERRORS))`
([Guía de configuración, nivel de tracing](guia-de-configuracion.md#nivel-de-tracing)).

El nivel es el dial propio de NarrativeTrace y está al frente: una llamada que
filtra nunca se convierte en evento, para ningún consumidor. El nivel de tu
logger es un segundo dial, independiente, que decide qué se *imprime* —
[FAQ, "Two dials, two paths"](../faq.md#two-dials-two-paths) es la versión
larga, y la distinción importa aquí porque subir el nivel de un logger te
ahorra volumen de log sin cambiar nada de la captura.

## El escenario

La ejecución es la reproducción del pago rechazado de
[Ayúdame a depurar y arreglar este error](ayudame-a-depurar-y-arreglar-este-error.md) —
`reserve`, luego `charge` lanzando una excepción, luego `release` — reutilizada
sin cambios, porque el tema de esta página es el dial y no otro flujo. El
driver de abajo la ejecuta en ambos niveles, y ejecuta también un checkout
*exitoso* en ambos:

```python
def _cost() -> dict[str, Run]:
    """The declined-payment reproduction at both levels, and a checkout that succeeds at both."""
    declined = "test_the_stock_is_released_when_the_card_is_declined"
    return {
        "cost_detail": _at_level("detail", "declined_payment", declined),
        "cost_errors": _at_level("errors", "declined_payment", declined, level="ERRORS"),
        "cost_detail_successful": _at_level("detail-successful", "checkout_review"),
        "cost_errors_successful": _at_level("errors-successful", "checkout_review", level="ERRORS"),
    }


def _at_level(directory: str, module: str, test: str | None = None, level: str = "DETAIL") -> Run:
    """One fixture run into its own directory, at ``level`` (the default level is DETAIL)."""
    return _run_fixture(module, _settings(COST, directory, NARRATIVETRACE_LEVEL=level), test)
```

Cada llamada es un proceso de pytest real con `narrativetrace-pytest` cargado,
en un directorio propio, con `NARRATIVETRACE_LEVEL` establecido como lo
establecería un despliegue.

## La salida real

**En `DETAIL`**, la ejecución rechazada, con cada valor capturado:

```text
---
type: trace
run: jumpy brick arcs
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

**En `ERRORS`**, la misma ejecución del mismo código:

```text
---
type: trace
run: limp pond mixes
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

- **OrderService.place_order**(customer_id: ``, sku: ``, quantity: ``, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: ``, quantity: ``) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: ``, amount_cents: ``, card: ``) #1.2

    > ❌ `PaymentDeclinedError`: card declined by the issuer — 0ms
  - **InventoryService.release**(sku: ``, quantity: ``) → `null` — 0ms #1.3
  - ❌ `PaymentDeclinedError`: card declined by the issuer
```

**Y en `ERRORS`, un checkout que tuvo éxito**: ningún artefacto en absoluto.
No hay nada que incrustar, que es justamente el punto — las pruebas de recetas
de este repositorio afirman ambas mitades de esa afirmación, la ausencia del
fichero en `ERRORS` y su presencia en `DETAIL`, de modo que el vacío es obra
del nivel y no de una ruta que nunca fue la correcta.

## Cómo leerlo

- **Qué conserva `ERRORS`.** La ejecución fallida, entera. `#1` lanzó una
  excepción, y el subárbol de un nodo de error se conserva intacto — así que
  `reserve` (`#1.1`), `charge` (`#1.2`) y `release` (`#1.3`) siguen todos ahí,
  incluidas las dos llamadas que retornaron con normalidad. Es deliberado: las
  llamadas alrededor de un fallo son lo que necesitas para diagnosticarlo, y
  descartar al hermano exitoso te dejaría con una excepción y sin historia. Una
  llamada que retornó *y* no conduce a ningún fallo por debajo se descarta, y
  una raíz sin ningún fallo en todo su subárbol se descarta por completo — por
  eso el checkout exitoso no escribió nada.
- **Qué descarta `ERRORS`.** Cada valor de parámetro: donde `DETAIL` imprimió
  `customer_id: "C-1234"` en un code span, `ERRORS` imprime `customer_id:` y un
  code span vacío. El valor nunca se renderizó, así que no se puede recuperar
  de estos eventos después, a ningún nivel posterior. Lo que sobrevive es la
  forma, los resultados (`reserve` y `release` siguen diciendo `→ null`) y la
  excepción, y `card_number` sigue leyéndose `[REDACTED]` porque la ocultación
  es una decisión distinta de la supresión.
- **La poda ocurre después de la captura, no en lugar de ella.** Cada llamada
  se interceptó y cada evento se publicó; después se construye el árbol y se
  elimina lo que el nivel no conserva. Esa es la forma honesta del coste:
  `ERRORS` es más barato que `DETAIL` porque no se renderizan los valores — la
  parte cara — no porque haya llamadas sin interceptar.
- **Solo `OFF` se salta la intercepción.** En `OFF`, la comprobación de
  `context.is_active()` del wrapper retorna antes de que ocurra cualquier
  captura, evento o publicación, y nada aguas abajo puede traer la llamada de
  vuelta — una prueba de este repositorio afirma que una llamada en `OFF` deja
  vacía la traza capturada. `ERRORS`, `SUMMARY` y `NARRATIVE` siguen
  interceptando todas las llamadas. Si la pregunta es "cuánto cuesta el
  trazado en este bucle caliente", la respuesta es otro nivel para ese ámbito,
  o `OFF`.
- **Los números.** No hay ninguno que citar, y esta página no escribe ninguno:
  la [sección Performance del README](../../README.md#performance) dice qué
  mide la suite de benchmarks y que todavía no se publican cifras oficiales, y
  ahí aparecerá cualquier cifra cuando la haya. Una copia que se mueve con las
  mediciones vale más que dos que no coinciden.

## Qué no se captura

- **No hay cifras publicadas en las que apoyarse.** Mide el nivel que piensas
  ejecutar: tu intérprete, tu hardware, la forma de tus parámetros (un grafo de
  objetos profundo tarda más en renderizarse que un `int`) y cuánto de tu
  código se traza mueven la respuesta.
- **Un nivel no es un control de privacidad.** `ERRORS` escribe menos valores
  porque los suprime, pero supresión y ocultación son mecanismos distintos con
  garantías distintas:
  [Mantén los secretos fuera de los logs](manten-los-secretos-fuera-de-los-logs.md)
  es la que se sostiene a todos los niveles.
- **Nada de aquí cambia cuánto escribe tu logger.** Cada evento capturado se
  sigue ofreciendo al puente de logging, así que el nivel propio del logger
  `narrativetrace` es lo que decide el volumen de log. Dos diales.
- **Un nivel no se puede subir con efecto retroactivo.** Los valores no
  capturados se pierden; reproducir la ejecución en `DETAIL` es la única vía de
  vuelta, que es lo que hace la receta de depuración.
- **Aquí no se muestran niveles por ámbito.** Esta página establece un solo
  nivel para toda una ejecución. Acotar en su lugar el ámbito trazado — qué
  objetos se envuelven siquiera — es la otra mitad de la pregunta del coste, y
  pertenece a [Eligiendo una integración](eligiendo-una-integracion.md).

**La skill para esto:** `narrativetrace-doctor` — informa del nivel al que
corre de verdad un proyecto, que es lo primero que hay que comprobar cuando una
traza es más delgada de lo esperado.
