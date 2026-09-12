<!-- source: documentation/what-to-commit.md blob 932b2f208abd | translated: 2026-09-12 | reviewed: - -->

# Qué commitear

Dos categorías, no una. Casi todo lo que escribe NarrativeTrace es un **artefacto generado que
describe una ejecución** — nada bajo tu directorio de salida configurado es código fuente, así que
nada de eso pertenece al control de versiones. La única excepción es la **traza aprobada**
(`.approved.nt`) *(since 0.1.2, unreleased)*: un humano la revisó y la aceptó como el contrato de
comportamiento, de la misma forma que el golden file de un snapshot test es una decisión, no una
salida — consulta la página [Formato de traza estructural](formato-de-traza-estructural.md) para la
gramática completa y el flujo de trabajo del modo de aprobación.

| Artefacto | Patrón de ruta | ¿Commit? | Por qué |
|---|---|---|---|
| Archivo de traza (Markdown, formato predeterminado) | `<OUTPUT_DIR>/traces/<Class>/<slug>.md` | No | Se regenera en cada ejecución |
| Archivo de traza (formato `text`/`mermaid`/`plantuml`) | `<OUTPUT_DIR>/traces/<Class>/<slug>.{txt,mmd,puml}` | No | Se regenera en cada ejecución |
| Documento de escenario JSON (solo formato Markdown) | `<OUTPUT_DIR>/traces/<Class>/<slug>.json` | No | La misma traza que el JSON canónico — se regenera en cada ejecución |
| Diagrama Mermaid complementario (solo formato Markdown) | `<OUTPUT_DIR>/diagrams/<Class>/<slug>.mmd` | No | Se regenera en cada ejecución |
| Array canónico de entradas | `<OUTPUT_DIR>/traces/<Class>/<slug>.canonical.json` | No | Un artefacto para máquinas usado en conformidad/portado, opcional mediante `NARRATIVETRACE_CANONICAL` |
| Traza estructural (`.nt`, la última línea base en verde) *(since 0.1.2, unreleased)* | `<OUTPUT_DIR>/structural/<Class>/<slug>.nt` | No | Se regenera en cada ejecución en verde — la copia de trabajo *local*, no la línea base revisada de abajo |
| **Traza aprobada** *(since 0.1.2, unreleased)* | `<APPROVED_DIR>/<Class>/<slug>.approved.nt` | **Sí**, en cuanto optas por el modo de aprobación | El contrato de comportamiento revisado — una decisión, no una salida |
| Traza recibida *(since 0.1.2, unreleased)* | `<APPROVED_DIR>/<Class>/<slug>.received.nt` | No | Se escribe ante una discrepancia (o si aún no hay línea base) para su revisión; se promueve con `uv run poe approve` / `narrativetrace-approve`, nunca se commitea |
| Traza incompleta *(since 0.1.2, unreleased)* | `<APPROVED_DIR>/<Class>/<slug>.incomplete.nt` | No | Se escribe en lugar de una traza recibida cuando la propia ejecución fue incompleta; el verbo approve la ignora por nombre |
| `manifest.json` *(since 0.1.2, unreleased)* | `<OUTPUT_DIR>/manifest.json` | No | Se regenera en cada ejecución — un índice sobre los artefactos anteriores, no una línea base en sí misma |
| Informe de claridad de la suite | `<OUTPUT_DIR>/clarity-report.md` | No | Un informe generado, no una decisión |
| Resultados de claridad de la suite | `<OUTPUT_DIR>/clarity-results.json` | No | Se genera junto con el informe |
| Salida del escáner independiente (CLI `narrativetrace-clarity`) | donde apunte `--output-dir` | No | Igual que lo anterior, se genera bajo demanda |
| `glossary.json` / `glossary.md` | raíz del repositorio (o donde apuntes `NARRATIVETRACE_GLOSSARY_DIR`) | **Sí**, si lo usas | Vocabulario de propiedad humana — el archivo commiteado es lo que lee la puntuación de claridad, y nunca se regenera con una ejecución de pruebas. "Un archivo, un flujo de revisión" |

El valor predeterminado de `<OUTPUT_DIR>` es `narrative-traces` y el de `<APPROVED_DIR>` es
`test-narratives` (ambos relativos a donde se haya ejecutado la suite, ambos configurables — ver la
[Guía de configuración](guia-de-configuracion.md)); ignora el directorio de salida y los dos
patrones de traza no aprobada bajo el directorio de aprobación:

```gitignore
narrative-traces/
test-narratives/**/*.received.nt
test-narratives/**/*.incomplete.nt
```

Si apuntas `NARRATIVETRACE_OUTPUT_DIR`/`NARRATIVETRACE_APPROVED_DIR` a otro lugar — un directorio
`build/`, una carpeta de artefactos de CI —, ignora esas rutas en su lugar. `glossary.json` y una
traza aprobada son las dos excepciones de esta lista: archivos que un humano escribe (o revisa y
acepta) y que una ejecución solo *lee*, nunca sobrescribe — eso es lo que los convierte en código
fuente.

## La regla en una frase

Si un archivo solo existe porque se ejecutó una prueba, es salida — no lo commitees. Si un archivo
existe porque un humano lo revisó y lo aceptó, es una línea base — commitéalo. `glossary.json` y
`.approved.nt` son las únicas dos filas de esta lista que un humano escribe o acepta; todo lo demás
se regenera.

## El modo de aprobación, visualmente

```text
la prueba pasa
   |
   v
compara la estructura actual con la traza aprobada
   |
   +-- igual    --> pasa, no se escribe nada
   +-- distinta --> escribe una traza recibida y falla
                    |
                    v
               un humano revisa el diff
                    |
                    v
             uv run poe approve  (o narrativetrace-approve)
                    |
                    v
             .approved.nt actualizado, commitéalo
```

`.approved.nt` nunca contiene valores de parámetros ni de retorno — consulta el
[Formato de traza estructural](formato-de-traza-estructural.md) para la gramática completa.
