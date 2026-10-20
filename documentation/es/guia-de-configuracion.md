<!-- source: documentation/guides/configuration.md blob 4e3ceec743da | translated: 2026-10-20 | reviewed: - -->

# Configuración

## De dónde vienen los ajustes

Cada ajuste se resuelve mediante una única cadena. Gana la primera fuente
que tenga la clave:

1. **Entorno** — `NARRATIVETRACE_<KEY>` (la clave en mayúsculas, así que
   `output_dir` se lee como `NARRATIVETRACE_OUTPUT_DIR`)
2. **`narrativetrace.toml`** — claves en la raíz del documento
3. **`pyproject.toml`** — claves bajo `[tool.narrativetrace]`
4. **Valor predeterminado incorporado**

Los archivos de configuración se buscan subiendo desde el directorio de
trabajo. Gana el directorio más cercano que contenga alguno de los dos
archivos, y ahí se detiene la búsqueda.

**Tener dos fuentes de configuración en el mismo directorio es un error
fatal.** Si un directorio tiene tanto un `narrativetrace.toml` como un
`pyproject.toml` con una tabla `[tool.narrativetrace]`, la resolución
lanza `DuplicateConfigurationError` en lugar de elegir uno en silencio.
Un archivo mal formado sigue contando como una fuente declarada — una
configuración rota debe fallar de forma ruidosa, no decidirse al azar
como con una moneda al aire.

```toml
# narrativetrace.toml
level = "NARRATIVE"
output = true
output_dir = "narrative-traces"
format = "markdown"
```

```toml
# ...o en pyproject.toml — nunca ambos en el mismo directorio
[tool.narrativetrace]
level = "NARRATIVE"
output = true
```

```bash
# El entorno siempre gana, para anulaciones puntuales
export NARRATIVETRACE_LEVEL=OFF
```

## Nivel de tracing

La captura está controlada por un nivel de tracing, que se comprueba
*antes* de que ocurra cualquier renderizado. Los niveles son
acumulativos — cada uno incluye todo lo que está por debajo.

| Nivel | Captura |
|---|---|
| `OFF` | nada (los wrappers cortocircuitan; el camino más económico posible) |
| `ERRORS` | solo las rutas que terminaron en error o nunca se completaron |
| `SUMMARY` | los puntos de entrada más sus llamadas hoja y de error, con los frames intermedios colapsados |
| `NARRATIVE` | la estructura completa de llamadas con la prosa resuelta de `@narrated` |
| `DETAIL` | + valores de parámetros y de retorno (predeterminado) |

Los valores de los parámetros se descartan **en el momento de la
captura** por debajo de `DETAIL`, así que no se pueden recuperar después
a partir de una traza de nivel inferior. `ERRORS` y `SUMMARY` además
podan el árbol tras la captura.

Se puede establecer en código, en un archivo de configuración o mediante
el entorno:

```python
from narrativetrace import ContextVarNarrativeContext, NarrativeTraceConfig, TracingLevel

context = ContextVarNarrativeContext(NarrativeTraceConfig(level=TracingLevel.NARRATIVE))
```

`NarrativeTraceConfig.resolve()` ejecuta la cadena anterior para la
clave `level`. Los valores desconocidos o vacíos degradan al valor
predeterminado en lugar de lanzar una excepción — una mala configuración
nunca debe tumbar la captura consigo. Los nombres de nivel no distinguen
mayúsculas de minúsculas.

## Excluir bibliotecas y código generado

`trace_object` envuelve exactamente el objeto que le entregas: esa es la lista de inclusión, y no hay ningún import hook que la amplíe. Después, dos listas de exclusión deciden qué nunca se traza, cada una con su propio responsable:

1. **Integrada, no configurable.** Lo que estructuralmente nunca es un límite de negocio en Python. Ningún ajuste la reactiva y nunca se informa.
2. **Configurable, con un valor predeterminado incluido.** Elementos internos de bibliotecas y frameworks, nombrados por prefijo de módulo. Dar la clave `exclude` *reemplaza* el valor predeterminado (decide la presencia, como con cada clave de aquí); para ampliarlo, repite sus entradas.

```python
from narrativetrace import trace_object

service = trace_object(OrderService(), context)                     # envuelto: esta es la inclusión
service = trace_object(OrderService(), context, exclude="acme.fakes")  # ...salvo que su módulo esté excluido
```

```toml
# narrativetrace.toml (o [tool.narrativetrace]); NARRATIVETRACE_EXCLUDE fija la misma clave
exclude = "acme.fakes;unittest;pytest"     # delimitada por ';', o un arreglo TOML
```

Un objetivo excluido vuelve de `trace_object` sin envolver, así que sus llamadas se ejecutan sin trazar; la exclusión gana sobre el envoltorio. Los prefijos se comparan con el módulo que define el tipo del objetivo, en un límite de `.`: `acme.fakes` cubre `acme.fakes.deep` pero no `acme.fakesx`. Una línea en stderr lo avisa por cada prefijo coincidente, nunca por objetivo. `narrativetrace doctor` (`config.exclude`) imprime la lista efectiva y falla ante un valor que no se puede interpretar; hasta corregirlo se aplica el valor predeterminado.

**Lista 1 — integrada**

| Nunca se traza | Propiedad estructural |
|---|---|
| `builtins.*` | El tipo del objetivo lo define el propio intérprete (`list`, `dict`, `str`) |
| `functools.partial` | Un objeto `functools.partial` / `partialmethod`, como objetivo o como miembro |
| `types.BuiltinFunctionType` | Un miembro que aporta el runtime en C: funciones integradas, métodos integrados enlazados, method wrappers, slot wrappers, method descriptors |
| `<lambda>` | Un miembro cuyo `__name__` no es un identificador (`<lambda>`, `<genexpr>`) |
| `_name` | Un miembro `_privado` o `__dunder__`: maquinaria que el runtime llama por su cuenta |

Los envoltorios de `functools.lru_cache` y las funciones decoradas con `functools.wraps` no están en ella: un método de negocio con caché sigue siendo un límite que vale la pena ver.

**Lista 2 — el valor predeterminado incluido**

| Prefijo de módulo | Por qué se excluye |
|---|---|
| `unittest` | La plataforma de pruebas de la biblioteca estándar y, como `unittest.mock`, su biblioteca de mocks: una subclase `Mock` generada registra cada llamada que recibe |
| `mock` | El backport de `unittest.mock` en PyPI, con las mismas clases de mock generadas |
| `pytest_mock` | Los ayudantes de pytest-mock alrededor de `unittest.mock` |
| `pytest` | Los ayudantes propios del ejecutor de pruebas |
| `_pytest` | La implementación privada del ejecutor de pruebas, a la que llaman plugins y fixtures |
| `pluggy` | La maquinaria de llamada de hooks de pytest |
| `hypothesis` | Los ayudantes y estrategias propios del motor de pruebas basadas en propiedades |
| `coverage` | El trazador y los informes de coverage.py |
| `narrativetrace` | Los tipos de esta propia biblioteca: trazarlos sería trazar al trazador |
| `ddtrace` | El runtime de otro agente APM: evita la instrumentación recursiva cuando conviven |
| `opentelemetry` | El otro runtime APM con más probabilidad de convivir, por la misma razón |

## Dos diales, dos rutas

**Configuré el nivel de tracing en `DETAIL` pero no aparece nada en mis logs. O: configuré mi
logger en `WARNING` y la traza sigue apareciendo en mis artefactos de pytest. ¿Qué ajuste gana?**

Ambos, porque responden preguntas distintas. NarrativeTrace tiene dos diales, y llevar una traza
capturada a tu logger es un paso aparte de capturarla siquiera.

**Dial 1, el nivel de tracing, decide qué se captura.** `OFF`, `ERRORS`, `SUMMARY`, `NARRATIVE`,
`DETAIL` — acumulativos, cada uno incluye todo lo que está por debajo (la tabla de arriba). Es el
propio ajuste de NarrativeTrace, y actúa en dos puntos distintos, no en uno solo: en `OFF`,
`context.is_active()` es `False` y el wrapper de `trace_object` se salta la interceptación por
completo — la llamada envuelta se ejecuta sin tocar nada de la maquinaria de captura, y nada se
convierte en un evento, para ningún consumidor. Desde `ERRORS` en adelante, toda llamada *sí* se
intercepta y se registra — `ERRORS` y `SUMMARY` no se saltan la interceptación, podan el árbol
resultante *después* de la captura (descartando rutas sin error, colapsando frames intermedios);
solo por debajo de `DETAIL` los valores de los parámetros se omiten en el momento de la captura, y
no se pueden recuperar después, sin importar lo que haga el logger. Ningún otro ajuste puede
recuperar lo que `OFF` se saltó o lo que solo `DETAIL` captura.

**Dial 2, el nivel de tu logger, decide qué se imprime — una vez que una traza llega a tu
logger.** Por defecto, no llega ninguna: NarrativeTrace no escribe nada en `logging.getLogger
("narrativetrace")` (el nombre de logger que usa `LoggingTraceConsumer`) a menos que tú mismo
envíes una traza allí. Cuando lo haces, cada tipo de línea tiene su propio nivel por defecto: una
entrada y un retorno en `DEBUG` (la biblioteca estándar `logging` de Python no tiene un nivel
`TRACE` que refleje el de Java), una excepción en `WARNING` como `!! {type}: {message}
[{error_context}]`. El umbral de tu logger entonces hace lo que siempre hace — subirlo silencia
líneas. Nunca captura más, y nunca captura menos.

**Ahora las dos rutas, que es de donde viene la confusión.** La traza capturada — todo lo que
devuelve `capture_trace()`, y todo lo que depende de ella: los artefactos por prueba del plugin de
pytest, la línea base de aprobación `.nt`, el informe de claridad, la exportación por lotes de
OpenTelemetry de `TraceSpanExporter`, la narrativa renderizada — se escribe directamente en el
almacén de eventos propio del contexto en el momento en que cada método entra y sale. Esa
escritura nunca consulta tu logger, en ninguna dirección: un logger `narrativetrace` en `CRITICAL`
no la reduce, y tampoco lo hace la ausencia total de logger.

Enviar una traza capturada a tu logger es un paso aparte y explícito, a través de
`LoggingTraceConsumer`, y hay dos formas de hacerlo:

- **Repetición tras la captura** — `export_to_logger(trace)` envía un `TraceTree` ya terminado a
  través de un `LoggingTraceConsumer` privado en una sola llamada. Este es el camino que usan el
  [tutorial de 60 segundos](sesenta-segundos.md#envíala-a-tu-logger) y cada guía de este
  repositorio.
- **En vivo, a medida que ocurren los eventos** — adjunta un `LoggingTraceConsumer` como el
  listener síncrono de un `DualPathPipeline` que ensambles tú mismo, normalmente junto a un
  `BufferedEventConsumer` como su ruta de mejor esfuerzo (un anillo acotado, 65.536 eventos por
  defecto, con descarte de carga bajo presión, cada pérdida contabilizada — consulta
  [Concurrencia](../../README.md#concurrency)) para cualquier otro consumidor en vivo, incluido un
  `OtelTraceEventListener`, alimentado por el mismo flujo de eventos.

En cualquier caso, la línea de log y el artefacto de traza son dos lectores independientes de los
mismos eventos capturados. Subir el nivel del logger `narrativetrace` silencia líneas de log; no
puede tocar la salida de `capture_trace()`, porque esa salida nunca pasó por el logger.

**Dónde vive cada dial.**

| Dial | Dónde vive |
|---|---|
| Nivel de tracing | Variable de entorno `NARRATIVETRACE_LEVEL`; `level` en `narrativetrace.toml` o `[tool.narrativetrace]` en `pyproject.toml`; `NarrativeTraceConfig(level=TracingLevel.X)` en código |
| Umbral del logger | Configuración ordinaria de `logging` sobre `logging.getLogger("narrativetrace")` — el nombre que usa `LoggingTraceConsumer` por defecto |
| Nivel por tipo de línea | `LoggingTraceConsumer(levels={EventType.ENTRY: ..., EventType.RETURN: ..., EventType.EXCEPTION: ...})`, o el mismo argumento `levels=` pasado a través de `export_to_logger(trace, levels=...)` |

**Reglas prácticas.** Para reducir el volumen de logs, sube el umbral del logger
`narrativetrace`; la traza capturada queda intacta. Para reducir el tamaño de la traza, baja el
nivel de tracing — `ERRORS`/`SUMMARY` la podan después de la captura. Para reducir el overhead,
baja el nivel de tracing hasta `OFF`: ese es el único paso que se salta la interceptación en sí;
`ERRORS`, `SUMMARY` y `NARRATIVE` siguen interceptando y registrando cada llamada igual que
`DETAIL`, solo que renderizan menos valores y podan más después. El umbral del logger no cambia
nada en el coste de captura, a ningún nivel. Para mantener el tracing activo en producción pero
fuera de los logs, deja el nivel de tracing en `SUMMARY` o superior y, o bien no envíes trazas a
tu logger en absoluto, o envíalas y pon el logger `narrativetrace` en `WARNING`: en cualquier
caso, `capture_trace()` y todo lo que depende de ella permanecen completos.

## Ajustes de salida (plugin de pytest)

| Clave | Variable de entorno | Significado | Predeterminado |
|---|---|---|---|
| `output` | `NARRATIVETRACE_OUTPUT` | truthy → escribe artefactos por prueba | activado |
| `output_dir` | `NARRATIVETRACE_OUTPUT_DIR` | directorio de artefactos | `narrative-traces` |
| `format` | `NARRATIVETRACE_FORMAT` | `markdown` / `text` / `mermaid` / `plantuml` | `markdown` |
| `level` | `NARRATIVETRACE_LEVEL` | nivel de captura para el contexto del fixture | `DETAIL` |
| `glossary_dir` | `NARRATIVETRACE_GLOSSARY_DIR` | directorio que contiene el `glossary.json` confirmado en el repositorio, que se lee para puntuar la claridad del vocabulario (ver [guia-de-claridad.md](guia-de-claridad.md)) | directorio de trabajo |
| `canonical` | `NARRATIVETRACE_CANONICAL` | también escribe el array de entradas `<test>.canonical.json` por prueba | `false` |
| `approval` | `NARRATIVETRACE_APPROVAL` | truthy → verifica la estructura contra una traza aprobada confirmada en el repositorio | `false` |
| `approved_dir` | `NARRATIVETRACE_APPROVED_DIR` | directorio que contiene las trazas `*.approved.nt` confirmadas en el repositorio | `test-narratives` |

`output` está activado por defecto: el fixture `narrative_trace` escribe los artefactos de
cada prueba no vacía bajo `narrative-traces/` sin necesidad de ninguna configuración. Desactívalo con
`NARRATIVETRACE_OUTPUT=false` (`0`/`no`/`off` también funcionan, sin distinguir mayúsculas de
minúsculas) o `output = false` en un archivo de configuración — ver [que-commitear.md](que-commitear.md)
para añadir el directorio a tu `.gitignore`.

`glossary_dir` se lee exista o no un glosario: leerlo no cambia nada en
disco, así que no necesita activación explícita, y un repositorio sin el
archivo puntúa solo con los diccionarios integrados.

Los nombres de formato no distinguen mayúsculas de minúsculas. Solo
`markdown` escribe los archivos complementarios acoplados (una
exportación canónica `.json` hermana y un `.mmd` de Mermaid); `text`,
`mermaid` y `plantuml` reemplazan la traza en Markdown con ese único
artefacto.

`canonical` es independiente de `format`: una ejecución que eligió
`text` o `mermaid` para su artefacto legible por humanos igual le debe
sus entradas a un ejecutor de conformidad. El archivo es un array JSON
plano de entradas canónicas en el esquema `1.2`, un `method_enter` y un
`method_exit` por cada llamada trazada, cada una válida contra
`entry.schema.json`. Está desactivado por defecto porque es un artefacto
para máquinas — para otras implementaciones, fixtures de conformidad y traducción — no
algo para leer después de un fallo.

## Artefacto estructural y modo de aprobación

La ruta Markdown además escribe un artefacto estructural `.nt` libre de valores junto a la
narrativa — consulta el [Formato de traza estructural](formato-de-traza-estructural.md) para la
gramática. El archivo en disco es la **última línea base en verde**: una ejecución en verde la
avanza, una ejecución que no está en verde se compara contra ella pero nunca la sobrescribe, así
que cada delta se lee como "qué cambió desde la última vez que este escenario pasó". "Verde" es el
veredicto completo, no solo las aserciones — una prueba que pasó pero cuya estructura fue
*rechazada* por el modo de aprobación termina sin estar en verde, y su estructura no se escribe.
Rechazar un cambio, por tanto, deja la línea base donde estaba, y revertir el cambio no reporta
ningún delta.

`approval` activa el modo de aprobación: después de una prueba **que pasa**, la estructura libre
de valores del escenario se verifica contra la línea base confirmada
`<approved_dir>/<TestClassName>/<slug>.approved.nt`. Una línea base faltante o una diferencia
estructural hace fallar la prueba con un diff legible y escribe la estructura actual junto a la
línea base como `*.received.nt`. Revísala, luego promuévela con `uv run poe approve` (o el script
de consola `narrativetrace-approve`, que lee esta misma clave `approved_dir`). Las pruebas que
fallan nunca se verifican — la aprobación solo juzga una prueba que de otro modo habría pasado.

Cada ejecución también escribe `<output_dir>/manifest.json`: un objeto `run` de nivel superior
(`id`, `name` — la frase de tres palabras propia de la ejecución,
véase [La ejecución tiene un nombre](#la-ejecución-tiene-un-nombre) más abajo) seguido de una fila
por escenario trazado, nombrando su prueba, su número de invocación cuando el método se ejecutó
más de una vez, y cada artefacto que le pertenece:

```json
{
  "schema": "narrativetrace/scenario-manifest/1",
  "run": {
    "id": "a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4",
    "name": "bold elk soars"
  },
  "scenarios": [
    {
      "scenario": "find TENT",
      "testClass": "CatalogTest",
      "testMethod": "test_finds_it",
      "invocation": 2,
      "artifacts": {
        "trace": "traces/CatalogTest/test_finds_it-002-tent.md",
        "structural": "structural/CatalogTest/test_finds_it-002-tent.nt"
      }
    }
  ]
}
```

El pie de la suite imprime una línea más que resume el estado estructural de cada escenario:

```text
NarrativeTrace — Suite complete
  run: bold elk soars
  2 scenarios recorded
  Clarity: 100% high | 0% moderate | 0% low
  Reports: narrative-traces
  Since last green: 1 scenario unchanged · 1 changed: "Customer places order" (+1 call InventoryService.release)
```

El informe en consola de una prueba que falla imprime el delta estructural contra el artefacto de
la última ejecución en verde en lugar de la traza completa, cuando la estructura realmente cambió.

### La ejecución tiene un nombre

 Se genera un id de ejecución por cada sesión de pytest — el propio
hook `pytest_sessionstart` del plugin — un id con forma W3C, nunca una constante compartida — y su
frase de tres palabras (el mismo generador de nombres del que sale el nombre de un id de traza) es
el **nombre de la ejecución**. Aparece en:

- el pie de página de la suite en consola (`run: bold elk soars`, arriba);
- el objeto `run` de nivel superior de `manifest.json` (`id` y `name`, arriba);
- el frontmatter YAML de todo documento Markdown de traza (`run: bold elk soars`, junto a
  `scenario:`);
- el contexto análogo a MDC del puente de logging de la biblioteca estándar como `runName` para
  toda la sesión (consulta la [Guía de logging](guia-de-logging.md)), de modo que un solo grep
  encuentra las líneas de log de una ejecución.

El nombre de la ejecución y su id están protegidos por el mismo invariante que el propio nombre de
una traza: **nunca** llegan al texto estructural `.nt`, a una traza aprobada o recibida, al nombre
de un artefacto, ni a las claves por escenario del manifiesto — ejecutar la misma suite dos veces,
con dos nombres de ejecución distintos, produce ficheros `.nt` byte a byte idénticos y la misma
salida de delta en ambas ocasiones. El propio nombre de una traza (`trace: bold elk soars
(a1b2c3d)` en el renderer de consola/indentado, `The trace bold elk soars:` en prosa, la frase en
la línea de título del Markdown) es algo *distinto* — uno por traza, no uno por ejecución — y está
igualmente ausente del texto `.nt`.

## Identidad del servicio

Estampa metadatos del servicio en cada span para correlación:

```python
from narrativetrace import ServiceIdentity

context = ContextVarNarrativeContext(service_identity=ServiceIdentity("orders", "1.4.0", "prod"))
```

Solo el nombre es obligatorio; `ServiceIdentity("orders")` deja la versión y el entorno sin definir.
Si se omite por completo, el contexto lee esos tres valores del entorno:

| Variable de entorno | Se convierte en |
|---|---|
| `NARRATIVETRACE_SERVICE_NAME` | el nombre del servicio |
| `NARRATIVETRACE_SERVICE_VERSION` | la versión del servicio |
| `NARRATIVETRACE_ENVIRONMENT` | el entorno de despliegue |

Un nombre en blanco significa que no hay identidad —una versión o un entorno sin nombre se
ignoran— y una identidad pasada al contexto prevalece sobre el entorno. Son solo variables de
entorno: ninguna clave de `narrativetrace.toml` las lleva. Sin ninguna de las dos, cada traza dice
`unknown_service:python` en la plataforma y en OpenTelemetry. `narrativetrace doctor`
(`config.service-identity`) falla cuando el código que no es de pruebas construye un
`ContextVarNarrativeContext` y nada nombra el servicio.

## Ampliar los valores por defecto de la ocultación

Dos mandos, y hacen cosas distintas.

```bash
# AÑADIR al vocabulario integrado (subcadenas de nombres de campo separadas por comas)
export NARRATIVETRACE_REDACTION_ADDITIONALPATTERNS=betalingskort,kontonummer
```

```python
# REEMPLAZAR por completo el vocabulario integrado
ValueRenderer(redaction_policy=RedactionPolicy.of_patterns({"ssn", "internal_ref"}))
```

La variable de entorno es para quien *despliega* el servicio: no necesita reconstrucción y se lee
solo del entorno, no de `narrativetrace.toml` ni de `pyproject.toml`, al construir una política.
`of_patterns` es para quien *escribe* la aplicación. Se combinan: las adiciones siguen aplicándose a
una política construida con `of_patterns`, porque reemplazar el vocabulario es la opinión de una
aplicación sobre cuáles de sus propios campos son sensibles, no un permiso para deshacer la
ampliación de un despliegue. `RedactionPolicy.DISABLED` las ignora. Contrato completo:
[Privacidad y ocultación](privacidad-y-ocultacion.md).

> **Las adiciones son patrones de subcadena**, comparados exactamente como el vocabulario de
> subcadenas integrado. Una corta arrastra la trampa que las palabras por token evitan: añadir `id`
> oculta todos los identificadores de la traza.
