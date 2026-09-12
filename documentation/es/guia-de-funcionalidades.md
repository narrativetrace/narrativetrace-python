<!-- source: documentation/feature-guide.md blob 204e8092b4b7 | translated: 2026-09-12 | reviewed: - -->

# Guía de funcionalidades de NarrativeTrace (Python)

Lo que distribuye NarrativeTrace para Python, desde la perspectiva del usuario. Para el catálogo
completo de funcionalidades multiplataforma (todos los niveles, todas las plataformas), consulta
la guía de funcionalidades canónica:
<https://github.com/narrativetrace/narrativetrace-java/blob/main/documentation/feature-guide.md>.

**Etiquetas de estado** (mismo vocabulario que la guía canónica):

- **Gratis** — publicada y disponible en este repositorio, bajo la Business Source License 1.1
  (ver *Licencia* más abajo).
- **Pro** — publicada en NarrativeTrace Pro (nivel comercial, una
  distribución separada).
- **En desarrollo** — en construcción activa; el diseño ya está definido.
- **Planificada** — especificada, aún no iniciada; puede cambiar.

**Licencia.** La API y el formato de salida de NarrativeTrace son estándares abiertos
(Apache 2.0). Su runtime es gratuito y de fuente disponible (BSL 1.1, que se convierte en
Apache 2.0 cuatro años después de cada versión). Pro es comercial. Todo lo marcado como **Gratis**
aquí es ese runtime: gratuito para usar en producción, de fuente disponible, no de código abierto — el
[`LICENSE`](../../LICENSE) de la raíz es la autoridad.

La documentación por tema vive en [guides/](../guides). El *porqué* detrás de los mecanismos
específicos de Python — incluidas las alternativas rechazadas — se registra en un log de decisiones
interno, no publicado aquí.

---

## Captura la historia de tu código (tracing principal)

| Función | Estado | Notas |
|---|---|---|
| Captura narrativa automática — nombres de métodos, clases y parámetros, valores de retorno, tiempos, errores; sin sentencias de log | Gratis | `trace_object(obj, context)` + `ContextVarNarrativeContext`; los nombres se leen mediante `inspect.signature` |
| Decoradores de enriquecimiento — `@narrated("… {param} …")`, `@on_error(ExcType, "…")` apilable (gana el más específico), sobrescrituras de nombre `@traced` para `*args`, `@narrative_summary` | Gratis | [guia-de-decoradores.md](guia-de-decoradores.md) |
| Ocultación de datos sensibles — parámetros `@not_traced`, campos `not_traced_field(...)` / `__nt_not_traced__`, ocultación por patrón de nombre (`RedactionPolicy`) | Gratis | Los valores ocultos se renderizan como `[REDACTED]`, y ni siquiera se leen para los miembros marcados; una ruta de plantilla `@narrated`/`@on_error` que llega a un miembro oculto se resuelve con el mismo marcador, en cualquier profundidad de la ruta; un `NamedTuple` se introspecciona por nombre de campo en lugar de imprimirse como una colección posicional anónima, de modo que un campo oculto permanece oculto también un nivel de contenedor más adentro |
| Cinco niveles de captura (OFF → ERRORS → SUMMARY → NARRATIVE → DETAIL), modificables en tiempo de ejecución, canal de entorno `NARRATIVETRACE_LEVEL` | Gratis | Los nombres de nivel difieren de la implementación Java (SUMMARY/NARRATIVE frente a NARRATIVE/FLOW). Los valores de parámetro solo existen en DETAIL; la supresión ocurre en la captura, no en el renderizado |
| Niveles de doble puerta — el nivel de captura y el nivel de log son independientes | Gratis | [guia-de-configuracion.md](guia-de-configuracion.md) |
| Captura de concurrencia — `ForkJoinGroup` / `FireAndForgetGroup` sobre tareas de asyncio *y* `ThreadPoolExecutor`, propagación de snapshot de identidad completa, injerto entre tareas | Gratis | La historia se mantiene coherente cuando la ejecución no es secuencial |
| Propagación bidireccional — un snapshot lleva la traza *hacia* un hilo o tarea, y el trabajo trazado allí *regresa*: la pila que captura lo reporta desde el momento en que se publica, de forma transitiva a través de una cadena de saltos async | Gratis | La ubicación sigue el momento de envío (`submit`); el trabajo adoptado se etiqueta como `ConcurrencyKind.ASYNC`; los helpers que reemiten sus propios hijos pueden excluirse con `activate_without_adoption()`; acotado a 10.000 spans por pila, las entregas que exceden el límite se rechazan por completo y se reportan mediante `TraceLoss` |
| Identidad de traza — id de traza, nombres de traza legibles por humanos, derivación de id de historia/capítulo | Gratis | Alineado con el esquema canónico |
| Contrato de pureza — la introspección enumera los datos almacenados; los getters `@property` nunca se ejecutan; cada miembro invocado está acotado y aislado ante excepciones | Gratis | [guia-de-decoradores.md](guia-de-decoradores.md) |
| Captura a prueba de fallos — un renderer o exportador que lanza una excepción nunca oculta el resultado de negocio ni la excepción (métodos síncronos y `async`) | Gratis | |

## Conéctalo a tu stack (integraciones)

| Función | Estado | Notas |
|---|---|---|
| Envoltura explícita de objetos — `trace_object(...)` | Gratis | Sin import hooks ni monkey-patching; consulta el ADL de la plataforma |
| Plugin de pytest — fixture `narrative_trace`, narrativas de fallo, advertencias de plantilla, artefactos por prueba, resumen de la suite | Gratis | Se autorregistra mediante entry point; [guia-de-pytest.md](guia-de-pytest.md) |
| Middleware ASGI (Starlette/FastAPI) — captura/exportación en el límite de la petición, metadatos de petición y usuario, rutas excluidas, adopción de `traceparent` W3C | Gratis | [guia-de-fastapi-asgi.md](guia-de-fastapi-asgi.md) |
| Accesor de contexto con alcance de petición — `get_narrative_context()` (utilizable como `Depends` de FastAPI) | Gratis | |
| Inyección saliente de `traceparent` para `httpx` (hooks síncronos y async) | Gratis | Extra exclusivo de Python; cierra el ciclo entre servicios |
| Middleware WSGI (Flask) | Planificada (Gratis) | Mismo contrato de límite de petición que ASGI |
| Middleware de Django | Planificada (Gratis) | Mismo contrato de límite de petición que ASGI |

ASGI es la única integración web publicada hoy — Flask/WSGI y Django están Planificadas, no
simplemente sin documentar.

## Lee la historia (salidas)

| Función | Estado | Notas |
|---|---|---|
| Renderizadores de texto indentado, Markdown y prosa | Gratis | |
| Referencias de valor de traza — deduplicación de valores capturados repetidos, direccionada por contenido, con etiquetas legibles (`‹Hotel›=full` en la primera emisión, `‹Hotel›` después) | Gratis | `render.value_reference.ValueReferenceIndex` vía `MarkdownRenderer`. Las etiquetas provienen del campo de identidad del valor estructurado (name/id/description/…), nunca de uno oculto; la igualdad de bytes certifica la coincidencia; la contención dentro de otros valores capturados cuenta y se reemplaza. Solo Markdown |
| Deltas de valor dentro de la traza — una recaptura de la misma entidad, modificada, se renderiza como un diff contra la referencia (`‹Dinner›′{amount: 100.0→92.0, currency: "USD"→"EUR"}`) | Gratis | `render.value_delta.value_delta`. "La misma entidad" es el mismo nombre de tipo estructurado más un campo de identidad igual; solo campos escalares modificados (`StringVal`/`IntVal`/`FloatVal`/`BoolVal`/`InstantVal`/`NullVal`), nunca reconstruidos a partir del árbol estructurado. Un objeto anidado o una lista modificados, un conjunto de campos distinto, o un valor sin campo de identidad se renderizan completos exactamente igual que antes. Una variante modificada que a su vez se repite se define COMO el diff (`‹Dinner·2›=‹Dinner›′{…}`). Solo Markdown |
| Archivos de traza por prueba con `.json` y compañeros Mermaid `.mmd` | Gratis | activado de forma predeterminada *(since 0.1.2, unreleased)*, `NARRATIVETRACE_OUTPUT=false` lo desactiva; las trazas vacías no escriben nada |
| Exportación JSON canónica (forma de flujo de eventos) | Gratis | `export_json` / `export_document_json`; probado con round-trip, y validado contra el esquema `chapter-tree.schema.json` a partir de los bytes que el writer real escribió en disco |
| Esquema de capítulo por servicio (`nt.entryType` / `schemaVersion` / entradas historia-capítulo) | Gratis | `export_chapter_json`; validado contra `chapter.schema.json`. La correlación nunca se omite: `trace_id` se adopta/hereda/genera, `nt.storyId` recae en la primera llamada raíz (`Class.method`, o si no `unknown`), `nt.chapterId` en la historia, `nt.traceName` en el id resuelto — de modo que una traza capturada sin ningún span sigue siendo válida |
| Esquema canónico **1.2** — un único `SCHEMA_VERSION` para la forma de entrada, el sobre de capítulo y los atributos de OTel | Gratis | `nt.narrationTemplate` (1.1, el texto crudo de `@narrated` con los marcadores de posición intactos) más los campos de identidad de 1.2: `nt.package`, `nt.exceptionPackage`, `nt.returnType`, `type` de parámetro, `thread.name`/`thread.id`/`nt.threadVirtual`. `nt.instanceId`, `code.filepath`/`code.lineno` y los campos de recursos del proceso están declarados pero no se capturan (registrado en la lista de tareas privada) — los tres están desactivados por defecto también en Java |
| `.canonical.json` por prueba — el arreglo plano de entradas, un enter + un exit por llamada | Gratis | `NARRATIVETRACE_CANONICAL=1`, independiente de `format`. Los árboles sin contexto reciben ids de span secuenciales y un id de traza **generado** (identidad eager, ADR-014 del producto): los ids de span, historia y capítulo se derivan y son estables en bytes entre ejecuciones, mientras que `trace_id`/`nt.traceName` son únicos por captura y deben normalizarse mediante el normalizador de conformidad antes de comparar los goldens |
| Diagramas de secuencia — Mermaid + PlantUML | Gratis | `narrativetrace-diagrams` |
| Vistas de traducción de trazas — vuelve a renderizar una traza capturada en un idioma que el `glossary.json` versionado cubre; los identificadores se traducen con el original conservado al lado, los valores y mensajes de excepción son idénticos byte a byte, la ocultación queda intacta, un pie de "vacíos del glosario" nombra cada frase sin traducir | Gratis | `narrativetrace-glossary`; transmisión en vivo mediante `TranslationSubscriber` (un observador del pipeline junto a la ruta duradera de la traza, nunca un reemplazo) o un archivo por traza mediante `TranslationFileSink`; `./demo.sh --example <name> --lang es\|zh-CN` es el ejemplo incluido |
| Resúmenes de prueba en consola con puntuaciones de claridad | Gratis | |
| Resúmenes de flujo — rutas agregadas + frecuencias por punto de entrada | Planificada (Pro, acceso restringido) | Fase E3 del plan Enterprise |
| Diffs de migración — comparación de comportamiento antes/después | Planificada (Pro, acceso restringido) | Fase E3 del plan Enterprise |
| Grafos de dependencias en tiempo de ejecución (siempre llamado vs. condicional) | Planificada (Pro, acceso restringido) | Fase E4 del plan Enterprise |

## Conserva tu stack de logging (logging + observabilidad)

| Función | Estado | Notas |
|---|---|---|
| Puente con `logging` de la stdlib — eventos narrativos a través de tus handlers existentes bajo el logger `narrativetrace`, sobrescrituras de nivel por tipo de evento | Gratis | Enter/return en DEBUG, excepciones en WARNING; [guia-de-logging.md](guia-de-logging.md) |
| Enriquecimiento estilo MDC — `NarrativeContextFilter` estampa claves de correlación canónicas en cada registro; `request_log_scope` para claves a nivel de petición | Gratis | `traceId`/`spanId`/`nt.class`/`nt.method`/`nt.depth`/identidad del servicio |
| Processor de structlog que emite el mismo conjunto de claves | Gratis | `narrativetrace-structlog`; fuente única de vocabulario (`current_scope_keys()`) |
| Coexistencia con logs escritos a mano | Gratis | Elimínalos a tu propio ritmo |
| Exportación de spans de OpenTelemetry — listener de eventos en vivo + exportador de árbol por lotes, atributos `narrative.*` tipados, desalojo de huérfanos | Gratis | `narrativetrace-otel`; [guia-de-opentelemetry.md](guia-de-opentelemetry.md) |
| Pipeline de eventos — fan-out de doble ruta, buffer acotado, consumidor con hilo de drenaje, watchdog y descarte bajo carga | Gratis | El buffering/retención es gratuito por diseño (ADR-010 del producto) |
| Agregación de flujo de eventos — árbol agregado, hotspots, rutas/tasas de error, frecuencias de método/error (`EventAggregator`) | Pro | Reubicada el 2026-07-12 (Fase 31a) a la distribución comercial; aliméntala con `EventStore.events()` |

## Mejora el código (diagnósticos de claridad)

| Función | Estado | Notas |
|---|---|---|
| Puntuación de claridad — calidad de los nombres de métodos, clases y parámetros a partir de trazas reales (cinco scorers ponderados, diccionarios idénticos byte a byte a los de Java) | Gratis | [guia-de-claridad.md](guia-de-claridad.md) |
| División de claridad a nivel de suite + `clarity-results.json` / `clarity-report.md` mediante el plugin de pytest | Gratis | |
| Escáner de código fuente independiente — console script `narrativetrace-clarity`, no requiere pruebas | Gratis | |
| Vocabulario del proyecto en la puntuación — el glosario versionado extiende los diccionarios integrados | Gratis | Un solo archivo, un solo flujo de revisión: los verbos del `glossary.json` versionado puntúan como verbos de dominio, sus sustantivos como tokens de dominio. Se lee desde `narrativetrace.glossary_dir` (por defecto: el directorio de trabajo) una vez por sesión; la lectura es incondicional, a diferencia de la recolección. Los niveles integrados mantienen la autoridad — los verbos genéricos, prefijos booleanos, marcadores de posición sin significado, sinónimos obsoletos y términos `stale` nunca se promueven |
| Abreviaturas aceptadas — una sección `abbreviations` declarada a nivel raíz de `glossary.json` | Gratis | Esquema 2: `{"fx": "foreign exchange"}`. Solo un token listado deja de pedirse que se deletree por completo — un token que aparece dentro de un término versionado no, así que `calc total` conserva la sugerencia `calc` → `calculate`. Es de propiedad humana (la recolección nunca lo escribe, el merge lo conserva); se omite cuando está vacía, de modo que un glosario que no declara ninguna permanece idéntico byte a byte al esquema 1; los lectores lo aceptan en cualquier versión |
| Recolección de vocabulario — hook de la suite de pytest (opcional según la presencia de `glossary.json`, `NARRATIVETRACE_GLOSSARY=off/on` lo anula) fusiona términos nuevos y marca los usos de alias obsoletos como incidencias de claridad `non-canonical-term`, cada una con una sugerencia de renombrado mecánica | Gratis | Fusión solo aditiva (los campos de autoría humana nunca se sobrescriben); un `glossary-usage.json` volátil informa lo que encontró una ejecución, nunca se versiona |
| Escaneo estático del glosario — console script `glossary-scan`, no requiere ejecutar pruebas; también es el único lugar donde se recolectan las plantillas de narración `@narrated`/`@on_error` (una traza capturada ya tiene los valores interpolados) | Gratis | `narrativetrace-glossary`; una herramienta de escritura deliberada y opcional, no una puerta de CI |
| Puerta de CI opcional — `--min-score`, `--max-high-issues` | Gratis | Se recomienda el modo consultivo por defecto |

## Deja que los agentes de IA vean la verdad en tiempo de ejecución (integración con IA)

| Función | Estado | Notas |
|---|---|---|
| Documentación orientada a LLM (`llms.txt`, `llms-full.md`) | Gratis | |
| Handlers de herramientas de análisis MCP | Planificada (Pro, acceso restringido) | Fase E5 del plan Enterprise |

Nota: la separación de valores ocurre en el momento de la captura (ADR-002 del producto — por
debajo de DETAIL, los valores de parámetro nunca se registran), pero el segundo archivo de traza
*estructural* seguro para IA por prueba de la implementación Java todavía no tiene equivalente en Python;
el plugin de pytest escribe un único archivo con detalle completo por prueba.

## Nivel Pro (comercial)

El nivel Pro de Python se distribuye como una distribución comercial separada
(licencia propietaria, nunca publicada en PyPI). La agregación de flujo de eventos se
reubicó allí desde el núcleo gratuito de este repositorio el 2026-07-12 (Fase 31a, Etapa 2):
**`EventAggregator` — Pro**. Los resúmenes de flujo, los diffs de migración, los diagramas de
grafos de dependencias y los handlers de herramientas MCP están **Planificados (Pro, acceso
restringido)** — su ejecución espera un acuerdo comercial pagado sobre el stack de Python, según
el plan de implementación privado de ese repositorio (Fases E3–E5). Auditoría y
cumplimiento **no está planificado** para Python (Fase E6).

---

## Cómo mantener esta guía honesta

Adaptado de las reglas de la guía canónica:

1. Toda funcionalidad visible para el usuario dNarrativeTrace para Python aparece aquí, exactamente una
   vez, con un estado.
2. Una funcionalidad pasa a **Gratis**/**Pro** solo cuando está fusionada (merged), probada y
   documentada. "En desarrollo" significa que el diseño ya está definido y el trabajo está
   programado; "Planificada" significa que solo está especificada.
3. Los cambios que añaden o promueven una funcionalidad deben actualizar este archivo en el
   mismo commit.
4. Esta guía cubre únicamente lo que distribuye NarrativeTrace para Python. Las funcionalidades de todo
   el producto y sus estados multiplataforma viven en la guía canónica (enlazada al principio) —
   no bifurques sus filas aquí; registra solo la realidad del lado de Python (incluyendo las
   brechas, con honestidad).
