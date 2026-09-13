<!-- source: documentation/agent-skills.md blob c54d6ed07342 | translated: 2026-09-13 | reviewed: - -->

# Habilidades del agente

*(since 0.1.2, unreleased)*

NarrativeTrace incluye **habilidades** (*skills*): procedimientos cargables por un agente que
ejecutan comandos probados y condicionan su finalización a un paso `verify`, en lugar de
documentación que un agente podría leer o no. Una habilidad es deliberadamente delgada — la lógica
de comprobación, diagnóstico o generación vive en código de biblioteca probado; el trabajo propio
de la habilidad es saber cuándo actuar, invocar ese código probado e interpretar el resultado en
contexto.

## Dos habilidades: configuración y diagnóstico

- **`add-narrative-tracing`** — instala NarrativeTrace en un proyecto y lo lleva hasta su primera
  traza: instala con el toolchain real (`uv add narrativetrace`), envuelve un objeto, renderiza y
  ejecuta la primera traza, y luego conecta un logger real (el puente de `logging` de la
  biblioteca estándar). Termina ejecutando `uv run narrativetrace doctor` y entregando el control —
  la costura entre las dos habilidades.
- **`narrativetrace-doctor`** — solo diagnóstico, y **de solo lectura**: nunca edita, genera ni
  elimina un archivo. Ejecuta la CLI probada, lee su informe y recorre las partes que una simple
  salida de CLI no puede cubrir por sí sola: probar la ocultación en una prueba, leer una traza
  renderizada antes de hacer aserciones sobre ella, y el flujo de aprobación de trazas (marcado
  como no estudiado — su propia celda de evaluación todavía está pendiente).

Se combinan: un proyecto completamente nuevo empieza con `add-narrative-tracing`; un proyecto que
ya tiene NarrativeTrace instalado, donde algo no funciona, empieza con `narrativetrace-doctor`.
Cualquiera de los dos caminos termina en el doctor — es él quien posee el diagnóstico a partir de
ahí. Una habilidad posterior se encargará de la generación (escribir la prueba de ocultación que
hoy el doctor solo puede pedirte que añadas).

## La CLI `narrativetrace`

Ambas habilidades ejecutan `uv run narrativetrace doctor` — el verbo `doctor` de la CLI gratuita,
junto al script de consola `narrativetrace-approve` ya existente. De solo lectura, sin red,
`--json` para salida legible por máquina, código de salida `0` (limpio), `1` (hallazgos) o `2` (no
se pudo ejecutar). Once comprobaciones con identificadores estables y con puntos: las versiones de
intérprete/pytest frente a lo declarado, los ocho paquetes `narrativetrace-*` de acuerdo en una
sola versión, la ortografía de `NARRATIVETRACE_OUTPUT`, el registro del plugin de pytest, claves
desconocidas en `narrativetrace.toml`, un marcador de ocultación importado pero nunca usado, los
parámetros de un método `*args` colapsando en un único valor `args: [...]`, si la ocultación está
probada en una prueba, y diffs de trazas de aprobación obsoletos.

## Instalarlas

- **Claude Code**: los archivos `SKILL.md` renderizados viven en
  [`.claude/skills/add/`](../../.claude/skills/add/SKILL.md) y
  [`.claude/skills/doctor/`](../../.claude/skills/doctor/SKILL.md) en este repositorio. Copia
  cualquiera de los dos directorios en el `.claude/skills/<nombre>/` de tu propio proyecto y Claude
  los detecta por sí solo, invocables como `/narrativetrace:add` / `/narrativetrace:doctor` una vez
  empaquetados como plugin, o por nombre (`add-narrative-tracing` / `narrativetrace-doctor`)
  directamente.
- **Cualquier agente, cualquier plataforma**: todo agente que lee `AGENTS.md` ve el puntero
  siempre activo que el propio `AGENTS.md` de este repositorio lleva entre sus marcadores
  `<!-- narrativetrace:skills:start -->` — los nombres y descripciones de ambas habilidades, así
  que un agente que nunca pensó en buscarlas igual sabe que existen.
- **Codex, Gemini y un instalador automático** están en la hoja de ruta pero aún no construidos —
  hoy, copiar los archivos renderizados es el camino.

## Cómo se construyen

Ninguna habilidad se edita nunca a mano.
`packages/narrativetrace-skills/src/narrativetrace_skills/catalogue/add_narrative_tracing.py` y
`.../catalogue/narrativetrace_doctor.py` son las dos fuentes de verdad; `python
scripts/skills_render.py --fix` regenera `.claude/skills/add/SKILL.md`,
`.claude/skills/doctor/SKILL.md` y la sección propia de `AGENTS.md` de este repositorio a partir de
ellas, y `python scripts/skills_render.py --check` (integrado en `uv run poe check`) hace fallar la
compilación en cuanto cualquiera de los tres se desincroniza de la fuente tipada. Cada bloque de
código que muestra una página renderizada se incrusta desde código fuente real y probado, mediante
la misma convención de marcador `<!-- snippet: -->` que usa el resto de la documentación de este
repositorio — nunca un ejemplo escrito a mano. Una comprobación de Tier A mantiene fuera de ambas
páginas las citas a notas de planificación privadas: las frases de justificación se publican, la
cita que nombra la nota no.

## Evaluarlas

`packages/narrativetrace-skills/evals/` lleva la suite de Tier B (frases disparadoras, un caso de
camino feliz por habilidad, un caso de desviación para la comprobación de ocultación del doctor) —
nunca se ejecuta con `poe check`; el responsable la ejecuta a mano o desde el job nocturno, a
través de CLIs de suscripción, nunca la API medida. Consulta [su propio
README](../../packages/narrativetrace-skills/evals/README.md) para la política de los carriles
esporádicos (Codex/Gemini) y la matriz de promoción.

## Ver también

- [`narrativetrace-skills`](../../packages/narrativetrace-skills/README.md) — el paquete del
  catálogo tipado
- [Sesenta segundos](sesenta-segundos.md) — el recorrido de instalación y primera traza del que se
  extraen los pasos de `add-narrative-tracing`
- [Qué commitear](que-commitear.md) — el estado de las trazas de aprobación que comprueba el cuarto
  paso del doctor
