<!-- source: documentation/structural-trace-format.md blob 7baee63cf348 | translated: 2026-09-12 | reviewed: - -->

# Formato de traza estructural (`.nt`)

*(since 0.1.2, unreleased)*. El artefacto de traza estructural seguro para IA (ADR-002 del
producto): un archivo por escenario de prueba que contiene únicamente la *forma* del
comportamiento autorada por el desarrollador — cero valores en tiempo de ejecución. Este formato
es **multiplataforma**: cada implementación de NarrativeTrace emite el formato idéntico, que es lo
que permite que las trazas aprobadas y las fixtures de conformidad viajen entre plataformas. Esta
página refleja la propia especificación del formato estructural de la implementación de
referencia — la gramática de abajo es normativa e idéntica en cada lenguaje en el que se distribuye
este producto.

## Archivos y nombrado

| Archivo | Rol |
|---|---|
| `<output_dir>/structural/<TestClass>/<slug>.nt` | Emitido junto a la traza en Markdown; el archivo en disco es la **última línea base en verde** — una ejecución que no está en verde se compara contra él (delta en consola, informe de fallo) pero nunca lo sobrescribe. "Verde" es el veredicto completo: una prueba que pasó pero cuya estructura fue *rechazada* por el modo de aprobación termina sin estar en verde, así que una estructura rechazada nunca se convierte en la línea base y revertir el cambio no reporta ningún delta |
| `<approved_dir>/<TestClass>/<slug>.approved.nt` | Traza aprobada confirmada en el repositorio (opcional mediante `NARRATIVETRACE_APPROVAL=true`, directorio configurable vía `NARRATIVETRACE_APPROVED_DIR`, por defecto `test-narratives`) — una prueba que pasa cuya estructura difiere falla con un diff legible |
| `<slug>.received.nt` | Se escribe junto a la traza aprobada ante una discrepancia (o cuando aún no existe una traza aprobada); revísala, luego promuévela mediante `uv run poe approve` o el script de consola `narrativetrace-approve` |
| `<slug>.incomplete.nt` | El mismo contenido, escrito en lugar de `.received.nt` cuando la propia ejecución fue incompleta (la vía de mejor esfuerzo descartó eventos, o rechazó un scope async por haber alcanzado el límite de adopción). El verbo approve la ignora por nombre: una ejecución corta nunca debe convertirse en la línea base confirmada, o cada ejecución completa posterior se leería como si hubiera *añadido* llamadas. Una ejecución así se compara por contención de subsecuencia en lugar de por igualdad — las ausencias se toleran y se nombran, cualquier cosa añadida o reordenada sigue fallando |

La extensión del formato va al final (`.approved.nt`, convención de ApprovalTests) para que los
editores y visores de diff se enganchen a `.nt`. Nota: `.nt` colisiona con RDF N-Triples en algunos
mapas de resaltado de sintaxis; registra una anulación en `.gitattributes` donde importe.

### Identidad del artefacto (multiplataforma)

`<slug>` arriba es la **identidad del artefacto** de una invocación de prueba, y cada
implementación la deletrea de la misma forma — un artefacto escrito por una implementación se
encuentra bajo el mismo nombre en otra:

- Un método de prueba ordinario es su nombre convertido a slug: dividido por mayúsculas y por
  `_`, en minúsculas, con todo lo que esté fuera de `[a-z0-9_]` reemplazado por `_` —
  `customerPlacesOrder` → `customer_places_order`.
- Una invocación de una prueba que se ejecuta más de una vez (cualquier caso de
  `@pytest.mark.parametrize`, o un fixture parametrizado) añade `-<index>-<label>`: el número de
  invocación en base 1 rellenado con ceros a tres dígitos, seguido de la etiqueta legible de la
  invocación pasada por la misma regla de slug con las repeticiones de `_` colapsadas y los
  extremos recortados — `equipment_can_be_found-002-find_tent`. Una etiqueta que se convierte en
  slug vacío se descarta, dejando `equipment_can_be_found-002`.
- `-` es el separador precisamente porque el alfabeto del slug no puede producirlo. El índice —
  no la etiqueta — es lo que hace el esquema a prueba de colisiones: dos invocaciones siempre
  difieren en él, así que etiquetas que solo difieren en caracteres que una ruta no puede llevar
  igual obtienen archivos separados. La etiqueta es lo que hace legible el nombre.
- El nombre es estable entre ejecuciones, máquinas y procesos, que es lo que permite que el
  `.approved.nt` de una invocación se confirme en el repositorio siquiera. Donde un nombre supera
  el límite de 255 bytes por elemento de ruta, la mitad del *método* se trunca y se le añaden
  ocho caracteres hexadecimales del `String.hashCode` de Java sobre el slug completo —
  especificado, por tanto idéntico en todas partes; un hash por proceso invalidaría en silencio
  cada línea base que tocara.

Porque los nombres de artefacto se derivan en lugar de anunciarse, una ejecución también escribe
`<output_dir>/manifest.json`: una fila por escenario trazado, nombrando su prueba, su número de
invocación y cada archivo que le pertenece. Consúltalo cuando conozcas el escenario y quieras el
archivo.

> El encabezado `scenario:` de una invocación **no** es su nombre de visualización. Un id de
> `parametrize` interpola argumentos en el nombre de visualización de la prueba, así que este
> artefacto — el libre de valores — se titula por el método y el número de invocación en su lugar:
> `Equipment can be found #2`. Una prueba que se ejecuta una vez conserva el nombre de
> visualización que siempre tuvo, así que ninguna traza aprobada confirmada se mueve. El *nombre
> de archivo* sigue llevando la etiqueta convertida a slug, porque eso es lo que distingue dos
> invocaciones en disco, y `manifest.json` — un índice también sobre los artefactos que conservan
> valores — nombra el escenario tal como pytest lo mostró. Mantén los secretos fuera de los ids de
> parametrize.

## Contenido

```
scenario: Weekend trip settles with three transfers

- TripSettlementService.record_expense(trip_name, expense)
  - ExpenseValidator.ensure_valid(expense)
  - TripLedger.record_expense(trip_name, expense)
- TripSettlementService.settle_trip(trip_name) → value
  - TripLedger.expenses_of(trip_name) → value
  ~ fork [2]
    - BalanceCalculator.compute_balances(expenses) → value
    - StockService.check() → value
```

- **Encabezado:** `scenario: <nombre de prueba humanizado>` + línea en blanco. Nada más — sin
  resultado, sin ids/nombres de traza, sin fechas. Una invocación de una prueba que se ejecuta más
  de una vez es `scenario: <nombre de método humanizado> #<index>` — los argumentos de un id de
  parametrize nunca llegan a él.
- **Línea de llamada:** `NombreDeClase.nombre_de_metodo(nombre_param, nombre_param)` — solo
  nombres, en orden de captura, con dos espacios de sangría por nivel de profundidad.
- **Tipos de desenlace:** un retorno que no es `None` se renderiza como ` → value`; un retorno de
  tipo `None`/void: nada; una excepción lanzada ` !! NombreSimpleDeExcepcion` (el tipo es
  estructura; el mensaje es un valor y nunca aparece); una entrada sin igualar ` ?? incomplete`.
- **Concurrencia:** los grupos fork se renderizan como `~ fork [n]` y el trabajo adoptado desde una
  instantánea de contexto propagada (un hilo o una tarea de `asyncio` que recoge trabajo bajo una
  instantánea activada) se renderiza como `~ async [n]`, ambos con sus miembros **ordenados por
  `Clase.metodo`** — el orden de captura entre hilos/tareas es una elección del planificador, no
  comportamiento, así que el artefacto expresa el conjunto y anidamiento del trabajo concurrente y
  nunca su orden. Los grupos async se agrupan por el span que los lanzó, así que cada hijo async de
  una llamada es un solo grupo, y también aparecen al nivel raíz cuando el trabajo sobrevivió a
  quien lo llamó. El trabajo fire-and-forget se renderiza como `~ fire-and-forget` + sus hijos. Los
  nombres/ids de hilo nunca aparecen.
- **Excluido por diseño:** todos los valores de argumento/retorno, mensajes de excepción,
  duraciones, marcas de tiempo, identidad de hilo, ids de traza/span, nombres de traza, resultados
  de ejecución, y la narración (la narración resuelta incrusta valores).
- **Codificación:** UTF-8, LF, salto de línea final. Los identificadores pasan por saneamiento de
  caracteres de control.

## Garantías

1. **Determinista:** comportamiento idéntico ⇒ archivo idéntico byte a byte. Esto es lo que hace
   del artefacto la línea base para la traza aprobada y el formato golden para las fixtures de
   conformidad.
2. **Libre de valores:** cero superficie de inyección de prompts, cero PII, tokens mínimos —
   seguro de entregar a un agente de IA por defecto.
3. **División del trabajo:** el artefacto afirma la *forma* de comportamiento; la corrección de
   valores sigue siendo responsabilidad de las aserciones de la prueba. Un cambio que solo altera
   un valor de retorno con estructura idéntica no cambia el artefacto — por diseño.

## Brecha conocida

Esta implementación todavía no emite el hermano JSON libre de valores que algunas otras
implementaciones distribuyen (`<test>.structural.json`, un array con la forma de
`.canonical.json` con cada valor eliminado) — el formato de texto `.nt` de arriba es el único
artefacto estructural de esta implementación hoy. Registrado como trabajo futuro;
`.canonical.json` (el array de entradas JSON que conserva valores) no se ve afectado y continúa
llevando el detalle completo.

Implementado en este repositorio por `narrativetrace.render.structural.StructuralTraceRenderer`,
emitido por el plugin `narrativetrace-pytest` junto a los compañeros `.md`/`.json`/`.mmd` — ver la
[Guía de pytest](guia-de-pytest.md), la [Guía de configuración](guia-de-configuracion.md) y
[Qué commitear](que-commitear.md).
