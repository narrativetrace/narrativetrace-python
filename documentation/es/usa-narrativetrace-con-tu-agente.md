<!-- source: documentation/use-with-your-agent.md blob d89822d53ce8 | translated: 2026-10-10 | reviewed: - -->

# Usa NarrativeTrace con tu agente

NarrativeTrace incluye [habilidades de agente](habilidades-del-agente.md) — los procedimientos que un
agente sigue para instalar la biblioteca, leer una traza y diagnosticar una instalación — en el
formato abierto Agent Skills. Todas las plataformas de la tabla siguiente ya descubren las páginas que
`init` escribe en `.agents/skills`, así que hay un único conjunto de páginas y ninguna copia por
plataforma. Lo que cambia de una plataforma a otra es cómo una persona ajena al proyecto lleva las
páginas a un proyecto, y qué pequeño fichero apunta al agente hacia ellas antes de que se le ocurra
mirar.

## Plataformas de un vistazo

<!-- platform-table:begin -->
| Plataforma | Cómo se obtienen las habilidades desde fuera | Lo que encuentra el agente tras `init` | Evidencia | Verificado |
|---|---|---|---|---|
| Cursor | Instala el plugin desde el manifiesto `.cursor-plugin` del repositorio público, o ejecuta `uv run narrativetrace init` en el proyecto | las habilidades en `.agents/skills` (Cursor también lee `.claude/skills`) y la regla `.cursor/rules/narrativetrace.mdc` que apunta a ellas | carril Tier B `cursor` | 2026-10-10 |
| Replit | Importa el repositorio público desde GitHub (pega su URL, previsualiza las habilidades y añádelas), o ejecuta `uv run narrativetrace init` en el proyecto | las habilidades en `.agents/skills` y una sección de NarrativeTrace en `replit.md`, la memoria del proyecto que el agente de Replit lee primero | prueba manual | 2026-10-10 |
| Antigravity | Nada que instalar más allá del propio proyecto: ejecuta `uv run narrativetrace init` en el proyecto y haz commit de las habilidades (la CLI `agy` y el IDE las leen como habilidades del espacio de trabajo) | las habilidades en `.agents/skills`, que Antigravity lee como habilidades del espacio de trabajo, y la sección de `AGENTS.md`, que carga como reglas | carril Tier B `antigravity` | 2026-10-10 |
| GitHub Copilot | Nada que instalar aparte del propio repositorio: ejecuta `uv run narrativetrace init` en el proyecto y haz commit de las habilidades | las habilidades en `.agents/skills` (Copilot también lee `.claude/skills` y `.github/skills`) y la sección de `AGENTS.md` | prueba manual | 2026-10-10 |
| Claude Code | Añade el repositorio como marketplace de plugins e instala su plugin, o ejecuta `uv run narrativetrace init` en el proyecto | las habilidades en `.claude/skills` y `.agents/skills`, y la sección de `AGENTS.md` que importa `CLAUDE.md` | carril Tier B `claude` | 2026-10-10 |
<!-- platform-table:end -->

La tabla se genera a partir del registro de plataformas que leen el instalador y el doctor, así que
no puede contradecir lo que hace `init`. La columna Verificado es la fecha en que los datos de cada
fila se comprobaron por última vez contra la documentación de la propia plataforma; el comportamiento
de las plataformas cambia con rapidez, así que trata esa fecha como parte de la respuesta y la
documentación del proveedor como la autoridad.

## Los ficheros de aviso que escribe `init`

Un aviso es un pequeño fichero que la plataforma ya lee primero. Se escribe solo cuando el proyecto
muestra que la plataforma está en uso, nunca como copia de una página de habilidad, y nunca a través de
un enlace simbólico:

- **Cursor** — `.cursor/rules/narrativetrace.mdc`, una regla siempre aplicada que dice dónde están las
  habilidades, escrita solo cuando el proyecto tiene un directorio `.cursor/`. El plugin de Cursor
  incluye la misma regla.
- **Replit** — una sección marcada de NarrativeTrace en `replit.md`, la memoria del proyecto que el
  agente de Replit lee primero, escrita solo cuando el proyecto tiene `replit.md` o `.replit`. Es la
  misma sección que lleva `AGENTS.md`, con los mismos marcadores.
- **Antigravity, GitHub Copilot, Claude Code** — sin aviso. Leen `.agents/skills` y `AGENTS.md`
  directamente (Antigravity carga `AGENTS.md` como reglas; Claude Code también lee `.claude/skills`,
  que `init` escribe en todo proyecto).

Un aviso que ya es idéntico a lo que escribiría `init` se adopta en vez de rechazarse, un fichero que
no es nuestro se rechaza sin `--force`, y `uv run narrativetrace uninstall` elimina exactamente los
avisos que escribió. `uv run narrativetrace doctor` informa del aviso de cada plataforma detectada
como presente y vigente, o nombra lo que falta, está obsoleto o no es nuestro.

## Copiar a mano

Copiar funciona con cualquier plataforma, y es el único camino para un agente sin comando
`narrativetrace` propio:

- **Codex**: el catálogo renderiza
  [`.agents/skills/narrativetrace-doctor/`](../../.agents/skills/narrativetrace-doctor/SKILL.md) y los
  demás directorios de habilidades de la misma carpeta — la disposición que Codex CLI documenta para
  las habilidades propias de un proyecto. Su frontmatter lleva solo `name` y `description` (Codex no
  documenta claves `when_to_use` ni `allowed-tools`); el cuerpo de la página es idéntico. Copia el
  directorio pertinente en el `.agents/skills/<nombre>/` de tu propio proyecto y Codex lo reconoce del
  mismo modo.
- **Antigravity**: las habilidades del espacio de trabajo se leen de `.agents/skills/` (el antiguo
  `.agent/skills/`), así que sirve la misma copia en el IDE y en la CLI `agy`. Su instalador de
  plugins lee solo el directorio `skills/` de primer nivel de un plugin, que este repositorio no
  distribuye, así que no hay una vía `agy plugin install`.
- **Cualquier agente, cualquier plataforma**: todo agente que lea `AGENTS.md` ve la sección siempre
  activa que `init` escribe allí — el nombre y la descripción de las habilidades, de modo que un agente
  que nunca pensó en buscarlas igualmente sepa que existen.

## Evidencia

La fila de cada plataforma nombra la prueba que la respalda. Los carriles de Claude, Codex, Antigravity y
Cursor ejecutan el agente real de línea de comandos contra el prompt de instalación sobre un proyecto
de ejemplo, y un carril cuya CLI no está instalada se omite con una sola línea en lugar de fallar;
Replit y GitHub Copilot son pruebas manuales que registra el propietario. Los carriles, la política
esporádica de cuotas y la matriz de promoción se describen en
[Tier B — pruebas con LLM](../../packages/narrativetrace-skills-catalogue/evals/README.md).

## Relacionado

- [Habilidades del agente](habilidades-del-agente.md) — qué son las habilidades, cómo se construyen y el instalador
- [Guía de instalación](guia-de-instalacion.md) — la biblioteca en sí
