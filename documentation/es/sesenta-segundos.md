<!-- source: documentation/sixty-seconds.md blob c9e26b0afb36 | translated: 2026-09-13 | reviewed: - -->

# Ve una traza en 60 segundos

Sin líneas `logger.info(...)`, sin framework de pruebas, nada que abrir después — un script sencillo,
una ejecución, y la traza se imprime directamente en tu terminal. Todo lo de abajo se ejecutó de
verdad contra el paquete publicado en PyPI (`narrativetrace` 0.1.1) — la salida está pegada, no
imaginada.

## 1. Proyecto nuevo, instala el paquete

```bash
uv init myproject && cd myproject
uv add narrativetrace
```

## 2. El programa

`main.py` adopta un id de traza fijo — el mismo mecanismo que usa una frontera al estilo servlet
para una cabecera de traza entrante — únicamente para que la salida de esta página siempre nombre
la misma traza. Tu propio código nunca hace esto: una ejecución real genera un id de traza
aleatorio cada vez, y el nombre de tres palabras de más abajo se deriva de él, nunca de un nombre
que tú elijas.

```python
# main.py
from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, TraceId, trace_object


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


# Un id de traza fijo, adoptado para que la salida incrustada de esta página siempre nombre la
# misma traza. Una ejecución real genera uno aleatorio cada vez (nunca este — es la constante
# propia de esta DEMO, no el valor por defecto de la librería) mediante el mismo
# TraceId.adopt_trace_id que usa una frontera al estilo servlet para una cabecera de traza entrante.
DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(IndentedTextRenderer().render(context.capture_trace()))
```

## 3. Ejecútalo

```bash
uv run main.py
```

```text
trace: loose hook parks (a1b2c3d)

OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
```

`0ms` también es real — esta llamada corrió en menos de un milisegundo. Una máquina más lenta o un
método más pesado muestran un número mayor; lo importante es que siempre se mide, nunca se inventa.

No escribiste ni una sola sentencia de log. Esa línea vino del nombre del método (`place_order`), los
nombres de los parámetros (`customer_id`, `product_id`, `quantity`) y el valor de retorno real — la
información que tu código ya tenía.

## Qué acaba de pasar

- **`ContextVarNarrativeContext()`** es el contexto de captura — donde caen los eventos de
  entrada/retorno/excepción mientras se ejecuta tu código. Se propaga a través de `contextvars`, así
  que sigue a las tareas async y al trabajo de thread-pool sin que tengas que pasarlo tú mismo.
- **`trace_object(OrderService(), context)`** envuelve una instancia real. Cada llamada a un método
  público del wrapper se captura; el objeto de debajo queda intacto — sin clase base, sin decorador en
  `place_order` mismo, sin registro.
- **`context.capture_trace()` más un renderizador** convierte los eventos capturados en texto.
  `IndentedTextRenderer` es lo que acabas de ver; `MarkdownRenderer` renderiza la misma llamada como
  una viñeta de Markdown — la forma que `narrativetrace-pytest` escribe a disco por defecto — y
  `ProseRenderer` se lee como una frase. Misma traza, tres formas.

## Envíala a tu logger

La línea en la consola está bien para un script; en producción quieres la traza en el flujo de
logs que ya tienes. `export_to_logger` envía una traza ya capturada a tu logger en una sola
llamada *(since 0.1.2, unreleased)* — el puente hacia el `logging` de la librería estándar que
NarrativeTrace incluye; en la propia `0.1.1` publicada, reproduce `store.events()` a través de
`LoggingTraceConsumer` a mano):

```diff
 # main.py
--from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, trace_object
+-from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, TraceId, trace_object
+import logging
+import sys
+
+from narrativetrace import (
+    ContextVarNarrativeContext,
+    IndentedTextRenderer,
+    NarrativeContextFilter,
+    TraceId,
+    export_to_logger,
+    trace_object,
+)
 
 
 class OrderService:
     def place_order(self, customer_id, product_id, quantity):
         return f"ORD-{customer_id}-{product_id}-{quantity}"
 
 
 # Un id de traza fijo, adoptado para que la salida incrustada de esta página siempre nombre la
 # misma traza. Una ejecución real genera uno aleatorio cada vez (nunca este — es la constante
 # propia de esta DEMO, no el valor por defecto de la librería) mediante el mismo
 # TraceId.adopt_trace_id que usa una frontera al estilo servlet para una cabecera de traza entrante.
 DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")

+handler = logging.StreamHandler(sys.stdout)
+handler.addFilter(NarrativeContextFilter())
+logging.basicConfig(
+    level=logging.DEBUG, format="[%(traceName)s] [%(runName)s] %(message)s", handlers=[handler]
+)
+
 context = ContextVarNarrativeContext()
+context.adopt_trace_id(DEMO_TRACE_ID)
 service = trace_object(OrderService(), context)
 service.place_order("cust-1", "prod-42", 3)
 
-print(IndentedTextRenderer().render(context.capture_trace()))
+trace = context.capture_trace()
+print(IndentedTextRenderer().render(trace))
+
+export_to_logger(trace)
```

```bash
uv run main.py
```

```text
trace: loose hook parks (a1b2c3d)

OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
[loose hook parks] [] → OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
[loose hook parks] [] ← returned: "ORD-cust-1-prod-42-3"
```

(el tiempo varía — el `0ms` es lo que haya medido tu máquina, igual que arriba; la frase entre
corchetes es siempre la misma — la reproducción de `export_to_logger` conserva el id propio de la
traza capturada, así que aquí `traceName` nombra la misma traza fijada arriba, nunca una nueva).
`traceName` aparece poblado porque hay una traza activa;
`runName` está vacío aquí porque este script sencillo no pertenece a ninguna ejecución de suite de
pruebas — solo se completa bajo el fixture de `narrativetrace-pytest` (consulta [Guía de
configuración, § La ejecución tiene un
nombre](guia-de-configuracion.md#la-ejecución-tiene-un-nombre)). La misma traza ahora llega al
destino de logs que ya tenías; la línea de consola queda intacta. Quien use `structlog` obtiene el
mismo conjunto de claves desde `narrativetrace-structlog` — consulta la [Guía de
logging](guia-de-logging.md) completa para `NarrativeContextFilter`, las claves MDC y la
correlación a nivel de request.

## A continuación

| Quieres | Ve a |
|---|---|
| Trazas desde tu suite de pruebas en vez de un script | [Guía de pytest](guia-de-pytest.md) |
| Mantener un valor fuera de la traza | [Privacidad y ocultación](privacidad-y-ocultacion.md) |
| Una puntuación de claridad de nombres para este código | [Guía de claridad](guia-de-claridad.md) |
| Niveles de tracing, configuración de la salida, precedencia | [Guía de configuración](guia-de-configuracion.md) |
| Algo de lo anterior no funcionó como se muestra | [Solución de problemas](solucion-de-problemas.md) |
