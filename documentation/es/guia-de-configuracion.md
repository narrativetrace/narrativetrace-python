<!-- source: documentation/guides/configuration.md blob f45d36689e76 | translated: 2026-09-11 | reviewed: - -->

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
| `output` | `NARRATIVETRACE_OUTPUT` | truthy → escribe artefactos por prueba | activado |
| `output_dir` | `NARRATIVETRACE_OUTPUT_DIR` | directorio de artefactos | `narrative-traces` |
| `format` | `NARRATIVETRACE_FORMAT` | `markdown` / `text` / `mermaid` / `plantuml` | `markdown` |
| `level` | `NARRATIVETRACE_LEVEL` | nivel de captura para el contexto del fixture | `DETAIL` |
| `glossary_dir` | `NARRATIVETRACE_GLOSSARY_DIR` | directorio que contiene el `glossary.json` confirmado en el repositorio, que se lee para puntuar la claridad del vocabulario (ver [guia-de-claridad.md](guia-de-claridad.md)) | directorio de trabajo |
| `canonical` | `NARRATIVETRACE_CANONICAL` | también escribe el array de entradas `<test>.canonical.json` por prueba | `false` |

`output` está activado por defecto: el fixture `narrative_trace` escribe los artefactos de cada
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

## Identidad del servicio

Estampa metadatos del servicio en cada span para correlación:

```python
from narrativetrace import ServiceIdentity

context = ContextVarNarrativeContext(service_identity=ServiceIdentity("orders", "1.4.0", "prod"))
```
