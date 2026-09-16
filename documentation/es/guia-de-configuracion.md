<!-- source: documentation/guides/configuration.md blob 5ed1cdbfb499 | translated: 2026-09-13 | reviewed: - -->

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

## Ajustes de salida (plugin de pytest)

| Clave | Variable de entorno | Significado | Predeterminado |
|---|---|---|---|
| `output` | `NARRATIVETRACE_OUTPUT` | truthy → escribe artefactos por prueba | activado *(since 0.1.2)* |
| `output_dir` | `NARRATIVETRACE_OUTPUT_DIR` | directorio de artefactos | `narrative-traces` |
| `format` | `NARRATIVETRACE_FORMAT` | `markdown` / `text` / `mermaid` / `plantuml` | `markdown` |
| `level` | `NARRATIVETRACE_LEVEL` | nivel de captura para el contexto del fixture | `DETAIL` |
| `glossary_dir` | `NARRATIVETRACE_GLOSSARY_DIR` | directorio que contiene el `glossary.json` confirmado en el repositorio, que se lee para puntuar la claridad del vocabulario (ver [guia-de-claridad.md](guia-de-claridad.md)) | directorio de trabajo |
| `canonical` | `NARRATIVETRACE_CANONICAL` | también escribe el array de entradas `<test>.canonical.json` por prueba | `false` |
| `approval` | `NARRATIVETRACE_APPROVAL` | truthy → verifica la estructura contra una traza aprobada confirmada en el repositorio *(since 0.1.2)* | `false` |
| `approved_dir` | `NARRATIVETRACE_APPROVED_DIR` | directorio que contiene las trazas `*.approved.nt` confirmadas en el repositorio *(since 0.1.2)* | `test-narratives` |

`output` está activado por defecto *(since 0.1.2)* — la versión publicada en PyPI,
`0.1.1`, todavía lo trae desactivado: el fixture `narrative_trace` escribe los artefactos de cada
prueba no vacía bajo `narrative-traces/` sin necesidad de ninguna configuración. Desactívalo con
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

## Artefacto estructural y modo de aprobación *(since 0.1.2)*

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
(`id`, `name` — la frase de tres palabras propia de la ejecución, *(since 0.1.2)*,
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

```
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

*(since 0.1.2)* Se genera un id de ejecución por cada sesión de pytest — el propio
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
