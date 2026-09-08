<!-- source: documentation/first-10-minutes.md blob 461cb9d3e2b7 | translated: 2026-09-03 | reviewed: 2026-09-03 -->

# Primeros 10 minutos

Un servicio diminuto, una prueba de pytest, siete pasos. Cada comando de abajo se ejecutó de verdad contra esta
versión del repositorio — las rutas de archivo, las puntuaciones de claridad y el marcador `[REDACTED]` son
salida real, no ilustraciones. Lo único que va a diferir en tu máquina es la
duración (`ms`) y el `trace_name` de dos palabras, generados de nuevo en cada ejecución.

Python ≥ 3.12. Si aún no ejecutaste la demo, `uv run poe demo --example ecommerce --no-pause`
desde la raíz del repositorio es aún más rápido — esta página es para cuando quieres verlo contra *tu
propio* código.

## 1. Instala el plugin de pytest

```bash
uv add --dev narrativetrace-pytest
```

Eso es toda la configuración de dependencias: el plugin trae consigo el core, `narrativetrace-diagrams` y
`narrativetrace-clarity` (el paso 6 de abajo usa su script de consola), y se registra con pytest
automáticamente mediante un punto de entrada — no hay que añadir nada a `conftest.py`.

## 2. Añade un servicio

```python
# order_service.py
class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"
```

Sin interfaz, sin clase base, sin registro. `trace_object` envuelve directamente cualquier objeto concreto.

## 3. Añade una prueba

```python
# test_order_service.py
from narrativetrace import trace_object

from order_service import OrderService


class TestOrderService:
    def test_customer_places_order(self, narrative_trace):
        service = trace_object(OrderService(), narrative_trace)
        service.place_order("C-1234", "SKU-KB", 2)
```

`narrative_trace` es un fixture — solicítalo y obtienes un contexto de captura nuevo, que se destruye (y,
con la salida habilitada, se escribe en disco) al final de la prueba.

## 4. Ejecuta la suite

```bash
NARRATIVETRACE_OUTPUT=1 uv run pytest -s
```

```text
.Scenario: Test customer places order

Execution trace:
OrderService.place_order(customer_id: "C-1234", product_id: "SKU-KB", quantity: 2) → "ORD-C-1234-SKU-KB-2" — 0ms
Trace written: narrative-traces/traces/TestOrderService/test_customer_places_order.md


NarrativeTrace — Suite complete
  1 scenarios recorded
  Clarity: 100% high | 0% moderate | 0% low
  Reports: narrative-traces
1 passed in 1.00s
```

> El eco "Execution trace" por prueba es salida estándar normal, así que la captura por defecto de pytest
> lo oculta a menos que pases `-s` (o que la prueba falle). El resumen final de la suite siempre se imprime — pasa
> por el hook terminal-summary de pytest, que evita la captura. Consulta
> [Solución de Problemas](solucion-de-problemas.md).

## 5. Abre la narrativa

`narrative-traces/traces/TestOrderService/test_customer_places_order.md`:

```markdown
---
type: trace
scenario: Test customer places order
entry_point: OrderService.place_order
duration_ms: 0
trace_id: aa4ae2eaa56e7e49b7aa42aece5999f0
trace_name: muted stone tests
method_count: 1
error_count: 0
---

## Trace: OrderService.place_order

**Scenario:** Test customer places order
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, product_id: `"SKU-KB"`, quantity: `2`) → `"ORD-C-1234-SKU-KB-2"` — 0ms
```

Cada valor en el flujo de llamadas — los valores de los parámetros, el valor de retorno — proviene de la llamada que
realmente hiciste. Nada se escribió a mano. `duration_ms: 0` también es real: esta llamada se ejecutó en menos de un
milisegundo, y se muestra como un número entero, no se oculta.

## 6. Renombra `place_order` a `process` y observa cómo cae la claridad

La calidad de los nombres se mide, no se afirma. El escáner independiente (el mismo que `poe check` conecta
a la puerta de este propio repositorio) lee el código fuente directamente, sin necesidad de ejecutar pruebas:

```bash
uv run narrativetrace-clarity order_service.py --min-score 0.5 --max-high-issues 0 --output-dir clarity-out
```

```text
Clarity analysis complete: 1 classes scanned
Output: clarity-out
```

`clarity-out/clarity-report.md`:

```markdown
| Scenario | Score |
|----------|-------|
| OrderService | 0.89 |
```

Renombra el método (la definición y el sitio de la llamada) a `process` y ejecuta el escáner de nuevo con un
umbral que bloquearía un job real de CI:

```bash
uv run narrativetrace-clarity order_service.py --min-score 0.8 --max-high-issues 0 --output-dir clarity-out
```

```text
OrderService: overall 0.68 below --min-score 0.80
1 HIGH-severity issues exceed --max-high-issues 0
Clarity analysis complete: 1 classes scanned
Output: clarity-out
```

El comando ahora sale con `1`. `clarity-out/clarity-report.md` muestra exactamente por qué:

```markdown
### OrderService

## Scores

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Method Names | 0.10 | 0.30 | 0.03 |
| Class Names | 0.91 | 0.20 | 0.18 |
| Parameter Names | 0.92 | 0.25 | 0.23 |
| Structural | 1.00 | 0.15 | 0.15 |
| Cohesion | 0.90 | 0.10 | 0.09 |
| **Overall** | **0.68** | | |

| Severity | Category | Element | Suggestion |
|----------|----------|---------|------------|
| HIGH | method-name | `OrderService.process` | Use a domain-specific verb+noun (e.g., calculateTotal, reserveInventory) |
```

Misma llamada, mismos valores, todo igual salvo el nombre — la puntuación global cayó de 0.89 a 0.68,
solo la dimensión de nombres de método cayó de 0.81 a 0.10, y apareció una incidencia de severidad HIGH con una
sugerencia concreta. Consulta la [Guía de Claridad](guia-de-claridad.md) para ver el modelo de puntuación completo. Vuelve a
renombrarlo a `place_order` (o a algo todavía más específico) antes de continuar.

## 7. Añade `@not_traced` y observa la ocultación

```python
from narrativetrace import not_traced, trace_object


class OrderService:
    @not_traced("payment_token")
    def place_order(self, customer_id, product_id, quantity, payment_token):
        return f"ORD-{customer_id}-{product_id}-{quantity}"
```

Pasa un token en la prueba (`service.place_order("C-1234", "SKU-KB", 2, "tok_live_51H8x9J")`) y ejecuta
de nuevo. La traza:

```text
- **OrderService.place_order**(customer_id: `"C-1234"`, product_id: `"SKU-KB"`, quantity: `2`, payment_token: `[REDACTED]`) → `"ORD-C-1234-SKU-KB-2"` — 0ms
```

El nombre del parámetro todavía aparece — puedes ver que *sí* se pasó un token — pero su valor nunca llega
al disco. Consulta [Privacidad y Ocultación](privacidad-y-ocultacion.md) para ver qué más cubre la ocultación y la
única forma documentada de acotarla.

## Adónde ir a continuación

| Quieres | Ve a |
|---|---|
| Un camino de integración distinto al fixture de pytest de arriba | [Eligiendo una Integración](eligiendo-una-integracion.md) |
| El contrato de privacidad fila por fila | [Privacidad y Ocultación](privacidad-y-ocultacion.md) |
| Qué archivos generados commitear | [Qué Commitear](que-commitear.md) |
| Algo de lo anterior no funcionó como se muestra | [Solución de Problemas](solucion-de-problemas.md) |
| Cada opción de configuración | [Guía de Configuración](guia-de-configuracion.md) |
</content>
</invoke>
