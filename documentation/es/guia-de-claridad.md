<!-- source: documentation/guides/clarity.md blob 27a21b6573d8 | translated: 2026-09-07 | reviewed: - -->

# Claridad

Como la traza *es* tus nombres, `narrativetrace-clarity` puntúa la calidad de los nombres de forma
objetiva y puede hacer fallar la CI cuando los nombres se desvían.

## Puntuar una traza

```python
from narrativetrace_clarity import analyze

result = analyze(context.capture_trace())
print(result.overall_score)          # 0.0 (deficiente) … 1.0 (excelente)
for issue in result.issues:          # ordenadas por impacto
    print(issue.severity.name, issue.category, issue.element, "→", issue.suggestion)
```

Cinco dimensiones ponderadas: nombres de métodos (0.30), nombres de clases (0.20), nombres de
parámetros (0.25), estructural (0.15), cohesión (0.10). Las puntuaciones se basan en diccionarios
idénticos byte a byte compartidos entre los runtimes de NarrativeTrace: 1053 verbos en 34 categorías de dominio, 187
abreviaturas, 35 mapas de colocaciones y sufijos de rol.

Las incidencias se clasifican por banda de puntuación (HIGH ≤ 0.20, MEDIUM ≤ 0.50), se deduplican
por `category|element` sumando las ocurrencias, y se ordenan por impacto.

## Tu propio vocabulario, a partir del glosario que ya tienes

Los diccionarios integrados conocen el inglés general del software. No saben que `fold` es un verbo
de tu dominio, que `tranche` es un sustantivo preciso, o que `fx` es la abreviatura que tu equipo ha
aceptado — y un nombre que no conocen se puntúa como desconocido, no como específico del dominio.

Se los enseñas con el archivo de vocabulario que tu repositorio ya tiene: el `glossary.json`
comiteado (ADR-012). No hay un segundo archivo de diccionario que mantener sincronizado.

| Entrada del glosario | Tipo | Qué aprende la claridad |
|---|---|---|
| `settle trade` | `verb-phrase` | `settle` es un verbo del dominio; `trade` es un sustantivo del dominio |
| `credit tranche` | `noun-phrase` | `credit` y `tranche` son sustantivos del dominio |
| `fx` | `word` | `fx` es un sustantivo del dominio |

Los términos de varias palabras enseñan un token a la vez, porque los identificadores se puntúan un
token a la vez. Todo contexto delimitado contribuye: un identificador no lleva una ruta de módulo,
así que el alcance por contexto no puede aplicarse en el momento de la puntuación.

### La abreviatura aceptada tiene su propia sección

Qué abreviaturas acepta tu proyecto es una decisión independiente de qué palabras usa su dominio,
así que vive en su propia sección de nivel raíz de `glossary.json` (esquema 2):

```json
{
  "schemaVersion": 2,
  "contexts": { "trading": { "packages": ["acme.trading"] } },
  "abbreviations": { "fx": "foreign exchange", "calc": "calculate" },
  "terms": []
}
```

Un token listado ahí nunca necesita desarrollarse. Un token que simplemente *aparece dentro de* un
término comiteado no: comitear la frase nominal `calc total` enseña que `calc` y `total` son
sustantivos del dominio, y no dice nada sobre si `calc` es abreviatura aceptada — así que la pista
`calc` → `calculate` sobrevive para el resto del repositorio.

La sección es de propiedad humana: la recolección nunca la escribe, y fusionar una recolección la
transporta intacta. Un glosario que no declara ninguna queda marcado con `"schemaVersion": 1` y
escribe exactamente los mismos bytes que escribía antes de que la sección existiera, así que
adoptar la funcionalidad no genera ruido en el diff. Los lectores aceptan la sección en cualquier
versión de esquema.

Los diccionarios integrados conservan su autoridad. Un proyecto puede enseñar a los puntuadores una
palabra que no conocen; no puede anular una que sí conocen — los verbos genéricos (`process`,
`handle`) y los prefijos booleanos (`is`, `has`) se quedan donde están; los marcadores sin
significado (`temp`, `foo`) no se rescatan por estar escritos; y los sinónimos obsoletos, las
entradas `template` y los términos `stale` nunca son vocabulario. Solo cuenta el archivo
*comiteado*: nada de lo que una ejecución recolecta realimenta las puntuaciones de esa misma
ejecución, lo que las haría no deterministas y autocertificadas.

```python
from narrativetrace_clarity import analyze
from narrativetrace_glossary import read_project_vocabulary

result = analyze(context.capture_trace(), read_project_vocabulary("."))
```

El plugin de pytest hace esto por ti, una vez por sesión: `narrativetrace.glossary_dir` (variable de
entorno `NARRATIVETRACE_GLOSSARY_DIR`) nombra el directorio, con el directorio de trabajo como valor
por defecto. La lectura es incondicional — no cambia nada en disco — y un glosario que no se puede
leer degrada a los diccionarios integrados con una advertencia, en lugar de hacer fallar la suite.

## La puerta de CI

El script de consola `narrativetrace-clarity` escanea las fuentes de Python (cada método público es
una raíz de profundidad 1) y escribe `clarity-results.json` + `clarity-report.md`:

```bash
narrativetrace-clarity src --min-score 0.5 --max-high-issues 0 --output-dir build/narrativetrace
# --format both|md|json   --warn-only   (formato desconocido → código de salida 2; por debajo del umbral → código de salida 1)
```

En este repositorio está integrado en `uv run poe check` a través de la tarea `clarity`.

## Agregación en tiempo de ejecución

El plugin de pytest puntúa el árbol capturado de cada prueba, imprime un pie de página
`Clarity: X% high | …`, y (con la salida habilitada) agrega una entrada de `clarity-results.json`
por cada prueba trazada.
