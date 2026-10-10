<!-- source: documentation/agent-skills.md blob e9b93aebce57 | translated: 2026-10-09 | reviewed: - -->

# Habilidades del agente

NarrativeTrace incluye **habilidades** (*skills*): procedimientos cargables por un agente que
ejecutan comandos probados y condicionan su finalización a un paso `verify`, en lugar de
documentación que un agente podría leer o no. Una habilidad es deliberadamente delgada — la lógica
de comprobación, diagnóstico o generación vive en código de biblioteca probado; el trabajo propio
de la habilidad es saber cuándo actuar, invocar ese código probado e interpretar el resultado en
contexto.

## Seis habilidades: configuración, diagnóstico, claridad, informes, verificación y depuración

- **`add-narrative-tracing`** — instala NarrativeTrace en un proyecto y lo lleva hasta su primera
  traza: instala con el toolchain real (`uv add narrativetrace`), conecta los frameworks que el
  proyecto ya usa aplicando cada corrección `config.<framework>-*` que imprime el doctor (la tabla
  de frameworks del propio doctor instalado decide cuáles, así que la página de la habilidad no
  nombra ninguno), envuelve un objeto, renderiza y ejecuta la primera traza, y luego conecta un logger real (el puente de `logging` de la
  biblioteca estándar). Ejecuta `uv run narrativetrace doctor` y entrega el control — la costura
  entre las dos habilidades — y termina *previsualizando* (nunca aplicando) `narrativetrace init`,
  para que la próxima sesión encuentre estas habilidades ya instaladas sin que nadie se lo diga.
- **`narrativetrace-doctor`** — solo diagnóstico, y **de solo lectura**: nunca edita, genera ni
  elimina un archivo. Ejecuta la CLI probada, lee su informe y recorre las partes que una simple
  salida de CLI no puede cubrir por sí sola: probar la ocultación en una prueba, leer una traza
  renderizada antes de hacer aserciones sobre ella, y el flujo de aprobación de trazas (marcado
  como no estudiado — su propia celda de evaluación todavía está pendiente).
- **`add-narrativetrace-clarity`** — añade a un proyecto la puerta de claridad de nombres y la lleva
  hasta dejarla limpia: instala `narrativetrace-clarity` como dependencia de desarrollo (`uv add
  --dev`), escanea los paquetes del proyecto, comprueba que el informe es **reciente y puntuó al
  menos una clase** — el escaneo termina con `0` y no escribe nada cuando no encuentra ninguna
  clase, así que un informe antiguo pasaría por uno nuevo —, renombra lo que el informe señala (en
  `snake_case`, sea cual sea el estilo de los ejemplos de la sugerencia), ejecuta las pruebas del
  proyecto y vuelve a ejecutar la puerta con los umbrales propios del proyecto hasta que termina con
  `0`. Nunca baja un umbral, nunca añade `--warn-only` y nunca recolecta un glosario solo para leer
  vocabulario. La puerta de este runtime lee código fuente de Python, así que no hay camino por el
  ejecutor de pruebas; un proyecto que versiona un glosario ejecuta el mismo escaneo a través de
  `narrativetrace_glossary.clarity_scan`.
- **`narrativetrace-feedback`** — informa de un defecto en el propio NarrativeTrace: una comprobación
  del doctor que es errónea o cuya corrección no funciona, un paso de una habilidad que no se puede
  seguir, una redacción del prompt de instalación que llevó a un lugar equivocado, o la biblioteca
  comportándose mal en un proyecto bien configurado. El verbo probado que hay detrás redacta el
  informe a partir del proyecto (las coordenadas de instalación, el propio informe JSON del doctor
  y, como máximo, una traza estructural), y **se niega a escribir un informe que lleve un valor de
  tus trazas** — nombrando la regla que lo rechazó, de modo que haya algo concreto que corregir en
  lugar de una advertencia que ignorar. Después la habilidad muestra el borrador completo y pregunta
  una sola vez si quieres presentarlo públicamente. No envía nada a ninguna parte y no presenta
  nada sin una respuesta dada en un turno propio.
- **`narrativetrace-verify`** — lee lo que un cambio hizo de verdad antes de que el agente diga que
  está terminado. Se ejecuta cuando las pruebas ya están en verde y primero decide si merece la pena
  trazar el cambio — una función pura o una edición de una sola clase no lo merecen, y la habilidad
  lo dice y se detiene. Si no, escribe la intención antes de ejecutar nada (qué colaboradores, en qué
  orden, en qué rama, cuántas veces), ejecuta el camino real más pequeño con las trazas activas (una
  prueba que usa el fixture `narrative_trace`), lee la traza estructural sin valores contra esa
  intención, abre valores solo en el span que parece incorrecto, corrige y vuelve a leer, y después
  fija el flujo como línea base `.approved.nt` — activa el modo de aprobación si está apagado,
  ejecuta toda la suite en modo de aprobación, muestra el `.received.nt` completo y solo lo promueve
  con `narrativetrace-approve` tras tu sí, en un turno propio. Su informe cita ids de span (`#2.1`),
  la posición que todas las variantes imprimen para la misma llamada, de modo que una afirmación
  sobre la traza se puede comprobar contra la traza.
- **`narrativetrace-debug`** — encuentra la causa de un resultado incorrecto leyendo lo que el
  código hizo con los valores, no recorriéndolo paso a paso. Empieza por un síntoma, no por un
  cambio: lo reproduce con la entrada más pequeña y las trazas activas, lee primero el diagrama de
  secuencia cuando el camino cruza hilos o tareas, y después nombra — por su id de span, antes de
  tocar código — el primer span cuyas entradas son correctas y cuyo resultado no lo es. Acota por
  span, nunca por fichero: lee el subárbol bajo ese id y, cuando el trabajo dentro del span no está
  trazado, envuelve un colaborador más con `trace_object` en lugar de ocultar nada
  (`not_traced_field`, `__nt_not_traced__` y `@not_traced` ocultan un valor; no delimitan una
  traza). Corrige el defecto en ese span, vuelve a ejecutar la misma entrada y comprueba que nada más
  se ha movido — una ejecución en rojo no escribe ningún `.nt`, así que la forma anterior a la
  corrección son las líneas de llamada del Markdown de la reproducción sin sus valores. Conserva la
  reproducción como prueba de regresión, fija su traza estructural con la misma puerta de aprobación
  que `narrativetrace-verify` e informa de la causa raíz por id de span. Cuando la traza y el código
  no coinciden, o el defecto es de NarrativeTrace, se lo pasa a `narrativetrace-feedback` en lugar de
  parchear alrededor.

Se combinan: un proyecto completamente nuevo empieza con `add-narrative-tracing`; un proyecto que
ya tiene NarrativeTrace instalado, donde algo no funciona, empieza con `narrativetrace-doctor`.
Cualquiera de los dos caminos termina en el doctor — es él quien posee el diagnóstico a partir de
ahí. `add-narrativetrace-clarity` es dueña del informe de nombres y de su puerta; no instala el
trazado. `narrativetrace-feedback` es donde acaba un camino cuando el problema resulta ser nuestro y no
del proyecto — la regla de cierre del propio doctor apunta a ella. `narrativetrace-verify` es lo que
hace una sesión con NarrativeTrace instalado después de cada cambio que merezca trazarse — el último
paso de la habilidad de instalación dirige a la siguiente sesión hacia ella, y el hallazgo
`config.approval-mode` del doctor (líneas base que nada compara) se corrige con su paso de fijación.
`narrativetrace-debug` es por donde empieza un síntoma reportado; comparte con la habilidad de
verificación su referencia de lectura (qué variante responde a qué pregunta, y las formas que
indican que algo salió mal) y su fijación, y termina en `narrativetrace-feedback` cuando el defecto
es nuestro. Una habilidad posterior se encargará de la generación (escribir la prueba de ocultación que
hoy el doctor solo puede pedirte que añadas).

## La CLI `narrativetrace`

Las dos primeras habilidades ejecutan `uv run narrativetrace doctor` — el verbo `doctor` de la CLI
gratuita, junto a `init`/`uninstall` ([Instalarlas](#instalarlas), más abajo), `feedback` (el verbo
que hay detrás de `narrativetrace-feedback`) y el script de consola `narrativetrace-approve` ya
existente. `doctor` es de solo lectura, sin red, `--json` para salida
legible por máquina, código de salida `0` (limpio), `1` (hallazgos) o `2` (no se pudo ejecutar).
Diecinueve comprobaciones con identificadores estables y con puntos: las versiones de
intérprete/pytest frente a lo declarado, los ocho paquetes `narrativetrace-*` de acuerdo en una
sola versión, la ortografía de `NARRATIVETRACE_OUTPUT`, el registro del plugin de pytest, si las
habilidades del agente de NarrativeTrace están instaladas y actualizadas, claves desconocidas en
`narrativetrace.toml`, un marcador de ocultación importado pero nunca usado, los
parámetros de un método `*args` colapsando en un único valor `args: [...]`, si la ocultación está
probada en una prueba, diffs de trazas de aprobación obsoletos, líneas base aprobadas que nada compara
porque el modo de aprobación está apagado, y una comprobación
`config.<framework>-*` por cada fila de la tabla de frameworks (la tabla y el cableado de cada
fila están en [`llms-full.md`](../llms-full.md#framework-table--what-the-doctor-checks)): un
framework que el proyecto usa cuya integración no está añadida, o está añadida pero nunca
cableada, falla con las líneas que hay que añadir; un framework sin integración publicada se
informa, nunca se adivina.

`feedback draft | url | gh` tiene tres canales sobre un mismo informe. `draft` escribe el informe
en `build/narrativetrace/feedback/` y lo imprime entero; `url` imprime la URL prerrellenada del
formulario de incidencias de `github.com/narrativetrace/narrativetrace-python`, que abres y
presentas con tu propia cuenta; `gh` imprime la línea exacta de `gh issue create`, solo cuando `gh`
está instalado y con la sesión iniciada, y nunca la ejecuta. Cada canal vuelve a redactar a partir
de las opciones que recibe, así que nada se presenta bajo un borrador que cambió después de
mostrarse. Código de salida `0` (redactado), `1` (el canal no está disponible, o el sistema de
archivos rechazó los archivos) o `2` (una regla `vf.*` libre de valores rechazó el informe y no se
escribió nada; o no se pudo leer la línea de comandos). Presentarlo es público: muestra que tu
proyecto usa NarrativeTrace.

## Instalarlas

El paquete `narrativetrace` (que `uv add narrativetrace` ya pone en tu `PATH`) lleva un verbo
`init` que instala las seis habilidades por ti — sin red, y sin escribir nada hasta que tú lo digas:

```bash
uv run narrativetrace init --dry-run
```

<!-- snippet: examples/sixty_seconds/build/agent-skills-init-preview.json -->
```json
{
  "carrier": "narrativetrace-skills==0.3.0",
  "actions": [
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-doctor/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/add-narrative-tracing/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-feedback/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/add-narrativetrace-clarity/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-verify/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-debug/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": "AGENTS.md",
      "status": "planned"
    }
  ],
  "exit_code": 0
}
```
<!-- /snippet -->

Ese es el sobre `--json`; sin la opción, el mismo comando imprime el plan como un diff unificado.
Léelo, y luego ejecútalo de nuevo sin `--dry-run` para escribir `.agents/skills/` (y también
`.claude/skills/`, en cuanto el proyecto tenga un directorio `.claude/` o un `CLAUDE.md`, o con
`--vendor claude`) más una sección marcada en `AGENTS.md`. `narrativetrace uninstall` elimina
exactamente lo que escribió y nada más; la comprobación `config.skills-installed` de
`narrativetrace doctor` avisa cuando lo instalado queda desactualizado, así que mantenerlo al día
más adelante es volver a ejecutar `init --dry-run`, no volver a copiar los archivos a mano.

Copiar los archivos renderizados a mano sigue funcionando, y es el respaldo para una plataforma sin
su propia convención de descubrimiento, o antes de haber añadido el paquete `narrativetrace`:

- **Claude Code**: los archivos `SKILL.md` renderizados viven en
  [`.claude/skills/add-narrative-tracing/`](../../.claude/skills/add-narrative-tracing/SKILL.md),
  [`.claude/skills/narrativetrace-doctor/`](../../.claude/skills/narrativetrace-doctor/SKILL.md),
  [`.claude/skills/narrativetrace-feedback/`](../../.claude/skills/narrativetrace-feedback/SKILL.md),
  [`.claude/skills/add-narrativetrace-clarity/`](../../.claude/skills/add-narrativetrace-clarity/SKILL.md),
  [`.claude/skills/narrativetrace-verify/`](../../.claude/skills/narrativetrace-verify/SKILL.md) y
  [`.claude/skills/narrativetrace-debug/`](../../.claude/skills/narrativetrace-debug/SKILL.md)
  en este repositorio — el nombre del directorio y el `name:` del frontmatter son siempre el id
  canónico del catálogo, nunca un segmento abreviado: un directorio `.claude/skills/` a nivel de
  repositorio es un espacio de nombres plano, no un plugin de Claude, así que un nombre abreviado
  (`doctor`) colisionaría con la habilidad de cualquier otro proveedor con ese mismo nombre. Copia
  cualquiera de los directorios en el `.claude/skills/<nombre>/` de tu propio proyecto y Claude los
  detecta por sí solo, invocables por nombre (`add-narrative-tracing` / `narrativetrace-doctor` /
  `narrativetrace-feedback` / `add-narrativetrace-clarity` / `narrativetrace-verify` /
  `narrativetrace-debug`) directamente.
- **Codex CLI**: los archivos `SKILL.md` renderizados viven en
  [`.agents/skills/add-narrative-tracing/`](../../.agents/skills/add-narrative-tracing/SKILL.md),
  [`.agents/skills/narrativetrace-doctor/`](../../.agents/skills/narrativetrace-doctor/SKILL.md),
  [`.agents/skills/narrativetrace-feedback/`](../../.agents/skills/narrativetrace-feedback/SKILL.md),
  [`.agents/skills/add-narrativetrace-clarity/`](../../.agents/skills/add-narrativetrace-clarity/SKILL.md),
  [`.agents/skills/narrativetrace-verify/`](../../.agents/skills/narrativetrace-verify/SKILL.md) y
  [`.agents/skills/narrativetrace-debug/`](../../.agents/skills/narrativetrace-debug/SKILL.md)
  en este repositorio — la propia documentación de descubrimiento de habilidades de Codex
  (verificada el 2026-09-14) escanea `.agents/skills/<name>/SKILL.md` desde el directorio de
  trabajo hasta la raíz del repositorio, así que esta es exactamente la ruta donde las encuentra,
  con los mismos nombres de directorio canónicos que los de Claude Code arriba. El frontmatter
  lleva solo `name` y `description` — los dos campos que documenta Codex — el cuerpo de la página
  debajo es idéntico byte a byte al de Claude Code.
- **Cualquier agente, cualquier plataforma**: todo agente que lee `AGENTS.md` ve el puntero
  siempre activo que el propio `AGENTS.md` de este repositorio lleva entre sus marcadores
  `<!-- narrativetrace:skills:start -->` — el nombre y la descripción de cada habilidad, así
  que un agente que nunca pensó en buscarlas igual sabe que existen.
- **Gemini** todavía no tiene una convención de descubrimiento de habilidades — está en la hoja
  de ruta, no construida.

## Desde un registro

Un proyecto puede llevar estas habilidades sin que nadie aquí haya ejecutado nunca `init`, en uno
de tres estados:

1. **Instalado por `init`** — commiteado, del equipo. El único estado que `config.skills-installed`
   aprueba: las páginas llevan la línea de procedencia y coinciden con el release que este
   proyecto resuelve.
2. **Una instalación personal desde un registro** (una caché de plugins de Claude Code) — solo
   tuya. Invisible para el doctor por diseño: diagnostica el proyecto, y una instalación personal
   no llega a ningún compañero de equipo ni a ningún otro agente.
3. **Una instalación de registro en el proyecto** (`npx skills add`) — las páginas renderizadas de
   este propio repositorio, aterrizadas por un registro en lugar de por `init`, así que todavía no
   llevan línea de procedencia.

Probar las habilidades tú mismo, sin tocar el proyecto:

```text
/plugin marketplace add narrativetrace/narrativetrace-python
/plugin install narrativetrace-python@narrativetrace-python
```

luego ejecuta `uv run narrativetrace init --dry-run`, lee el diff, y ejecútalo sin la opción para
que `AGENTS.md` apunte a ellas.

Instalar en el proyecto desde el registro de estándar abierto:

```text
npx skills add narrativetrace/narrativetrace-python
```

luego ejecuta `uv run narrativetrace init --dry-run`, lee el diff, y ejecútalo sin la opción para
que `AGENTS.md` apunte a ellas.

Una página que dejó un registro nunca se rechaza solo por estar ahí. `init` la compara, byte a
byte salvo por el fin de línea, contra lo que ella misma habría renderizado. Una idéntica a la
propia página de este release es **adoptada** — el plan lo dice así, en vez de "reemplazada",
porque quien lo lea tiene que saber que no se sobrescribió nada suyo. Este es el propio texto del
plan, citado, nunca retecleado aquí:

<!-- snippet: packages/narrativetrace-tooling/src/narrativetrace_tooling/init/plan_renderer.py region=adoptedNote -->
```python
ADOPTED = "adopted: identical to this carrier's page, so only the provenance line is added"
"""What the plan and the report say about a page that was already ours in everything but a line."""

```
<!-- /snippet -->

Una página que difiere — otro release, o editada a mano — conserva el rechazo ordinario para el
que está `--force`. `npx skills add` también deja `.claude/skills/<nombre>` como un enlace
simbólico a la página de estándar abierto; `init` nunca escribe a través de un enlace así. Un
enlace cuyo destino adoptaría o ya es suyo se reemplaza con un directorio real que lleva el flavor
correcto; cualquier otro enlace se rechaza, porque `--force` cubre contenido, nunca un enlace.

Y este es el propio arreglo del doctor, citado de la misma forma, para un proyecto donde las
páginas están pero no llevan nada de esto:

<!-- snippet: packages/narrativetrace-tooling/src/narrativetrace_tooling/doctor/checks/skills_installed.py region=registryMessages -->
```python
_INIT_COMMAND = "uv run narrativetrace init --dry-run"

_READ_THE_DIFF = f"Run `{_INIT_COMMAND}`, read the diff, then run it without the flag."

_FROM_A_REGISTRY = (
    " Pages that are there without our line usually came from a registry (npx skills add, a plugin"
    " or workspace install). A page identical to this release's is adopted, and no --force is"
    " needed."
)
"""What a page with no provenance line most often IS: a registry install of this repository's own
rendered pages (design D5 state 3). Naming the case matters because the obvious reading of "not
ours" is "somebody else's work", which invites a ``--force`` nobody needs."""

```
<!-- /snippet -->

## Cómo se construyen

Ninguna habilidad se edita nunca a mano.
`packages/narrativetrace-skills-catalogue/src/narrativetrace_skills/catalogue/add_narrative_tracing.py`,
`.../catalogue/narrativetrace_doctor.py`, `.../catalogue/narrativetrace_feedback.py` y
`.../catalogue/add_narrativetrace_clarity.py` son las
fuentes de verdad; `python scripts/skills_render.py --fix` regenera el
`.claude/skills/<nombre>/SKILL.md` de cada habilidad, su equivalente de Codex en `.agents/skills/`,
la sección propia de `AGENTS.md` de este repositorio, y `.claude-plugin/marketplace.json` — el
listado que convierte este repositorio en un marketplace de plugins de Claude Code — a partir de
ellas, y `python scripts/skills_render.py --check` (integrado en `uv run poe check`) hace fallar la
compilación en cuanto cualquiera de ellos se desincroniza de la fuente tipada. Cada bloque de
código que muestra una página renderizada se incrusta desde código fuente real y probado, mediante
la misma convención de marcador `<!-- snippet: -->` que usa el resto de la documentación de este
repositorio — nunca un ejemplo escrito a mano. Una comprobación de Tier A mantiene fuera de todas
las páginas las citas a notas de planificación privadas: las frases de justificación se publican,
la cita que nombra la nota no. Una segunda comprobación vigila la única línea de frontmatter cuya
ausencia es una virtud: una habilidad cuyos pasos pueden hacer algo público — hoy,
`narrativetrace-feedback` — no debe declarar `allowed-tools`, porque ese campo preaprueba las
herramientas listadas durante el turno que carga la habilidad, y una habilidad de informes que
preaprobara su propio comando de informes dejaría de hacer que el arnés pregunte justo donde
preguntar es el sentido. La página de Claude Code de una habilidad así no tiene ninguna línea
`allowed-tools`, en lugar de una vacía. Una tercera comprobación somete a la misma regla, por la
misma razón, a una habilidad que promueve una línea base de aprobación — hoy,
`narrativetrace-verify` y `narrativetrace-debug`: la promoción se ejecuta con
`uv run narrativetrace-approve`, y el sí que espera es el tuyo.

## Evaluarlas

`packages/narrativetrace-skills-catalogue/evals/` lleva la suite de Tier B (frases disparadoras, un
caso de camino feliz por habilidad, un caso de desviación para la comprobación de ocultación del
doctor; el camino feliz de la habilidad de claridad parte de un fixture cuyos nombres poco claros
señala la puerta, y se califica porque la puerta pasa limpia después) — nunca se ejecuta con `poe check`; el responsable la ejecuta a mano o desde el job
nocturno, a través de CLIs de suscripción, nunca la API medida. Consulta [su propio
README](../../packages/narrativetrace-skills-catalogue/evals/README.md) para la política de los
carriles esporádicos (Codex/Gemini) y la matriz de promoción.

## Ver también

- [`narrativetrace-skills-catalogue`](../../packages/narrativetrace-skills-catalogue/README.md) —
  el paquete del catálogo tipado
- [Sesenta segundos](sesenta-segundos.md) — el recorrido de instalación y primera traza del que se
  extraen los pasos de `add-narrative-tracing`
- [Qué commitear](que-commitear.md) — el estado de las trazas de aprobación que comprueba el cuarto
  paso del doctor
- [Privacidad y ocultación](privacidad-y-ocultacion.md) — la lista de denegación y las formas de
  valor frente a las que se miden las propias reglas libres de valores del informe de problemas
