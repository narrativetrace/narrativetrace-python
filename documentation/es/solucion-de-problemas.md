<!-- source: documentation/troubleshooting.md blob 1839b50194fe | translated: 2026-09-11 | reviewed: - -->

# Solución de problemas

Síntoma → causa → solución, para los modos de fallo que la gente realmente encuentra. Algunas
entradas son la explicación completa; otras remiten a la guía que ya la desarrolla con más detalle
en lugar de repetirla aquí — un único lugar por cada hecho.

## No se generan archivos de salida de trazas

**Causa:** la salida de artefactos está activada de forma predeterminada, así que algo la
desactivó — un `NARRATIVETRACE_OUTPUT=false` en el entorno o en CI, o `output = false` en
`narrativetrace.toml` / en la tabla `[tool.narrativetrace]` de `pyproject.toml` — o los archivos
están en un directorio distinto del que estás mirando.

**Solución:** elimina la desactivación y revisa `NARRATIVETRACE_OUTPUT_DIR` (predeterminado:
`narrative-traces/` bajo el rootdir de pytest) — consulta la [Guía de
configuración](guia-de-configuracion.md). Una traza vacía (un objeto envuelto cuyos métodos nunca
se llamaron) no escribe nada aunque la salida esté habilitada; no hay ningún archivo vacío que
encontrar.

## No veo la traza por prueba en mi terminal

**Causa:** el eco de "Execution trace" por prueba se escribe con un simple `print()`, y pytest
captura la salida estándar de forma predeterminada — una ejecución simple de `pytest` no muestra
nada en tu terminal aunque el archivo bajo `narrative-traces/` se haya escrito correctamente.

**Solución:** ejecuta con `-s` (`pytest -s`) para verla en vivo, o revisa el archivo directamente.
El resumen de pie de suite ("NarrativeTrace — Suite complete …") siempre se imprime,
independientemente de lo anterior, porque pasa por el hook `pytest_terminal_summary` de pytest,
que evita la captura.

## Los parámetros de un método con `*args` aparecen como un único valor `args: [...]`

**Causa:** `inspect.signature` puede vincular los nombres de los parámetros de una firma
ordinaria, pero un método que recibe `*args` no tiene nombres por argumento que leer — no hay nada
con nombre que reconstruir porque el propio Python no lo tiene.

**Solución:** añade `@traced("first", "second", ...)` para proporcionar los nombres
explícitamente:

```python
from narrativetrace import traced

class Calc:
    @traced("a", "b")
    def add(self, *args):
        return sum(args)
```

## `trace_object` envuelve el objeto, pero las llamadas siguen sin trazarse

**Causa:** en algún lugar tienes una referencia al objeto *original*, sin envolver —
`trace_object` devuelve un envoltorio nuevo; el objeto que pasaste no se modifica. Una llamada
hecha sobre esa referencia original, o sobre `self` desde dentro de un método no trazado, evita el
envoltorio por completo.

**Solución:** asegúrate de que cada llamador tenga el objeto que devolvió `trace_object(...)`, no
el que construiste. Normalmente esto significa envolver una sola vez, en una raíz de composición o
en una fixture, y pasar la referencia envuelta en todo el flujo posterior.

## Las trazas entre hilos o entre tareas están vacías, o un hijo bifurcado aparece como una nueva raíz

**Causa:** `ContextVarNarrativeContext` aísla los hilos *y* las tareas de asyncio por diseño — el
trabajo enviado a un thread pool o generado como una tarea solo se une a la traza padre si recibió
una instantánea del contexto, o si pasó por `ForkJoinGroup`/`FireAndForgetGroup`. Un worker que
nunca recibió ninguna de las dos cosas registra en su propio contexto separado. Por separado:
bifurcar directamente dentro de un método trazado `async def` resuelve el padre a través de la
pila de llamadas *síncrona*, que está vacía dentro de una corrutina, así que los hijos lanzados de
esa forma terminan como hermanos/raíces en lugar de anidados bajo el llamador `async` — una
limitación conocida y aún abierta.

**Solución:** toma una instantánea explícita en el límite correspondiente, o usa
`ForkJoinGroup.create(...)` / `FireAndForgetGroup.create(...)` desde un método síncrono (o uno
respaldado por un thread pool) en lugar de hacerlo directamente dentro de `async def`. Si solo
necesitas la traza propia del trabajo bifurcado, llama a `capture_trace()` dentro de la tarea, en
el hilo o la tarea que la registró.

## La puntuación de claridad parece incorrecta

**Causa:** normalmente se trata de un nombre genérico que el analizador marca — `get`, `set`,
`process`, `handle`, `data`, `info`, `temp` y similares puntúan bajo sin importar el contexto; un
nombre que tu equipo acepta como vocabulario del dominio pero que los diccionarios integrados no
conocen se puntúa como desconocido, no como específico del dominio.

**Solución:** revisa la lista de incidencias en `clarity-report.md` y, o bien renombra
(`getData()` → `fetchOrderHistory()`), o bien enséñale tu vocabulario al analizador mediante un
`glossary.json` versionado — consulta la [Guía de claridad](guia-de-claridad.md).

## `DuplicateConfigurationError` al iniciar

**Causa:** el mismo directorio tiene tanto un `narrativetrace.toml` como un `pyproject.toml` con
una tabla `[tool.narrativetrace]`. La resolución de configuración se niega a elegir uno
silenciosamente.

**Solución:** mantén exactamente una fuente de configuración por directorio — elimina o combina
una de las dos. Consulta la [Guía de configuración](guia-de-configuracion.md).

## El middleware de ASGI no captura una ruta que esperaba que omitiera, u omite una que esperaba que capturara

**Causa:** `excluded_paths` compara la ruta de la petición por coincidencia exacta de cadena, no
como un glob o un prefijo — excluir `/health` no excluye `/health/live`, y solo se capturan los
scopes HTTP (los scopes de WebSocket y de lifespan siempre pasan sin ser tocados).

**Solución:** enumera explícitamente cada ruta que quieras excluir, o haz la coincidencia antes,
en tu propia capa de enrutamiento, antes de que se ejecute el middleware. Consulta la [Guía de
FastAPI/ASGI](guia-de-fastapi-asgi.md).

## Aparece en una traza un valor que esperaba que estuviera oculto

**Causa:** la lista de denegación compara por el *nombre del campo o del parámetro*, no de forma
general con "todo lo que se llame `data`" — un valor guardado bajo un nombre que la lista de
denegación no reconoce (y que no tiene la forma de un JWT, un número de tarjeta, una cadena
`Set-Cookie` o un número de identidad nacional) no se oculta de forma predeterminada. Por
separado: una plantilla de narración
`{param.path}` siempre consulta la lista de denegación *predeterminada*, incluso si el
`ValueRenderer` que la rodea se construyó con una `RedactionPolicy` personalizada o deshabilitada
para el renderizado de parámetros simples — una limitación documentada, no un error.

**Solución:** marca el miembro explícitamente con `@not_traced(...)` / `not_traced_field(...)` —
el decorador explícito siempre tiene prioridad, sin importar la política. Consulta [Privacidad y
ocultación](privacidad-y-ocultacion.md) para conocer el contrato completo y verificado.
</content>
</invoke>
