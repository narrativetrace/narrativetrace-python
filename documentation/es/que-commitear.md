<!-- source: documentation/what-to-commit.md blob ab4d416d0d4f | translated: 2026-09-07 | reviewed: - -->

# Qué commitear

Todo lo que NarrativeTrace escribe hoy es un **artefacto generado que describe una ejecución** —
todavía no existe en esta implementación un archivo de línea base revisada (el formato estructural `.nt` del
implementación Java y su flujo de trabajo de approval testing están planeados aquí, pero aún no
implementados — consulta la [Guía de funcionalidades](guia-de-funcionalidades.md)). Hasta que eso
llegue, la regla es simple: nada bajo tu directorio de salida configurado es código fuente, así que
nada de eso pertenece al control de versiones.

| Artefacto | Patrón de ruta | ¿Commit? | Por qué |
|---|---|---|---|
| Archivo de traza (Markdown, formato predeterminado) | `<OUTPUT_DIR>/traces/<Class>/<slug>.md` | No | Se regenera en cada ejecución |
| Archivo de traza (formato `text`/`mermaid`/`plantuml`) | `<OUTPUT_DIR>/traces/<Class>/<slug>.{txt,mmd,puml}` | No | Se regenera en cada ejecución |
| Documento de escenario JSON (solo formato Markdown) | `<OUTPUT_DIR>/traces/<Class>/<slug>.json` | No | La misma traza que el JSON canónico — se regenera en cada ejecución |
| Diagrama Mermaid complementario (solo formato Markdown) | `<OUTPUT_DIR>/diagrams/<Class>/<slug>.mmd` | No | Se regenera en cada ejecución |
| Array canónico de entradas | `<OUTPUT_DIR>/traces/<Class>/<slug>.canonical.json` | No | Un artefacto para máquinas usado en conformidad/portado, opcional mediante `NARRATIVETRACE_CANONICAL` |
| Informe de claridad de la suite | `<OUTPUT_DIR>/clarity-report.md` | No | Un informe generado, no una decisión |
| Resultados de claridad de la suite | `<OUTPUT_DIR>/clarity-results.json` | No | Se genera junto con el informe |
| Salida del escáner independiente (CLI `narrativetrace-clarity`) | donde apunte `--output-dir` | No | Igual que lo anterior, se genera bajo demanda |
| `glossary.json` / `glossary.md` | raíz del repositorio (o donde apuntes `NARRATIVETRACE_GLOSSARY_DIR`) | **Sí**, si lo usas | Vocabulario de propiedad humana — el archivo commiteado es lo que lee la puntuación de claridad, y nunca se regenera con una ejecución de pruebas. "Un archivo, un flujo de revisión" |

El valor predeterminado de `<OUTPUT_DIR>` es `narrative-traces` (relativo a donde se haya ejecutado
la suite); añádelo a `.gitignore` de tu proyecto:

```gitignore
narrative-traces/
```

Si apuntas `NARRATIVETRACE_OUTPUT_DIR` a otro lugar — un directorio `build/`, una carpeta de
artefactos de CI —, ignora esa ruta en su lugar. `glossary.json` es la única excepción: vive donde
tú lo pongas (normalmente en la raíz del repositorio), nunca lo escribe una ejecución de pruebas, y
debe versionarse como cualquier otro archivo fuente.

## La regla en una frase

Si un archivo solo existe porque se ejecutó una prueba, es salida — no lo commitees.
`glossary.json` es el único archivo de esta lista que escribe un humano y que una ejecución
simplemente *lee* — eso es lo que lo convierte en la única excepción.

## Qué cambia cuando llega el approval testing

Los archivos `.approved.nt` / `.received.nt` de la implementación Java son una categoría
genuinamente distinta — una línea base estructural revisada por un humano es una decisión, no una
salida, y pertenece al control de versiones tal como lo hace el golden file de un snapshot test.
Esta implementación todavía no tiene ese mecanismo; cuando lo tenga, esta página ganará la misma división en
dos categorías que documenta Java (línea base revisada: commitear; todo lo demás: no) en lugar de
una reescritura desde cero.
