<!-- source: documentation/guides/decorators.md blob c4f5e00e06e9 | translated: 2026-09-17 | reviewed: - -->

# Guía de decoradores

Envolver un objeto con `trace_object` traza cada método público. Los decoradores refinan qué se
captura y cómo se lee.

## Ya importaste esto — así se aplica

Importar `narrated` o `not_traced` no hace nada por sí solo — cada uno tiene que aplicarse a un
método o parámetro real, y el resultado tiene que probarse con una aserción. El emparejamiento
mínimo de ambos, apilados en un solo método tal como ya lo hace `AuthService` en
`packages/narrativetrace/tests/test_trace_object.py`:

```python
from narrativetrace import (
    ContextVarNarrativeContext,
    ProseRenderer,
    narrated,
    not_traced,
    trace_object,
)


class AuthService:
    @narrated("login attempt for {username} with {password}")
    @not_traced("password")
    def login(self, username: str, password: str) -> str:
        return f"session-for-{username}"


def run() -> str:
    """Traces one login and renders the result -- `password` never reaches it, in the argument
    list or in the narration template that names it."""
    context = ContextVarNarrativeContext()
    service = trace_object(AuthService(), context)
    service.login("alice", "hunter2")
    return ProseRenderer().render(context.capture_trace())
```

```text
The trace damp shard sways:

The auth service login — login attempt for alice with [REDACTED], returning "session-for-alice".
```

La aserción que lo demuestra: `assert "[REDACTED]" in rendered` — `password` nunca llega al texto
de narración que `@narrated` construye a su alrededor, y una aserción vecina comprueba que
`username`, el argumento no oculto, sigue presente (`examples/test_import_and_use.py`).

`uv run narrativetrace doctor` vigila exactamente este fallo en el código fuente de un proyecto:
**`trap.silent-sink`** marca las superficies de ocultación de campo de abajo (`not_traced_field`,
`__nt_not_traced__`) importadas o declaradas pero nunca aplicadas de verdad — llama a
`not_traced_field(...)` sobre un campo real o enumera nombres de campo reales en
`__nt_not_traced__`, y después demuéstralo aseverando `"[REDACTED]"` en una traza renderizada — y
**`trap.redaction-proof`** marca un proyecto sin ninguna prueba que asevere el marcador literal
`[REDACTED]`. Ambos decoradores, y ambas superficies de ocultación de campo, en detalle a
continuación.

## `@narrated` — narración en prosa

```python
from narrativetrace import narrated

class InventoryService:
    @narrated("reserves {quantity} of {product_id}")
    def reserve(self, product_id: str, quantity: int) -> Reservation:
        ...
```

Los tokens de plantilla `{name}` y un nivel con punto, `{customer.address}`, se resuelven a partir
de los valores de los parámetros; una ruta más profunda, como `{customer.address.city}`, nunca
puede resolverse y sobrevive de forma literal en tiempo de ejecución, por lo que un marcador de
posición que la nombre igualmente emite una advertencia de la suite por token sin resolver.

**La ocultación prevalece sobre una plantilla que lo nombra.** Una ruta que llega a un miembro
oculto — en cualquier profundidad de la ruta, no solo en su último segmento — se resuelve como
`[REDACTED]` en lugar del valor o del marcador de posición literal. Un `{nombre}` simple que nombra
un valor directamente obedece las mismas dos reglas: la lista de denegación lee esa clave
exactamente como lee un nombre de campo, y también se comprueba la forma del propio valor, así que
`@narrated("login {password}")` y un JWT que llega como `{value}` se renderizan ambos como
`[REDACTED]`. Nombrar una ruta, o un valor, nunca debilita las reglas que se aplican directamente
al valor: si necesitas el valor en una narrativa, quita
`@not_traced` del miembro; esa eliminación es la decisión deliberada y revisable, y queda reflejada
en el diff.

## `@on_error` — contexto de fallo

Se puede apilar; adjunta un mensaje resuelto a una salida fallida para el tipo de excepción
coincidente:

```python
from narrativetrace import on_error

class PaymentService:
    @on_error(TimeoutError, "gateway timed out charging {customer_id}")
    def charge(self, customer_id: str, amount: int) -> Payment:
        ...
```

## `@not_traced` — ocultación

Oculta un parámetro por nombre:

```python
from narrativetrace import not_traced

class AuthService:
    @not_traced("password")
    def login(self, username: str, password: str) -> Session:
        ...
```

Oculta un **campo** de un objeto pasado como argumento, de dos maneras:

- **`not_traced_field(...)`** — un campo de dataclass, marcado mediante los metadatos de su propio
  `field()`.
- **`__nt_not_traced__`** — un atributo de clase que nombra los campos a ocultar, para cualquier
  otro tipo de objeto: una clase simple, un `NamedTuple`, o una clase de attrs, en cualquier sitio
  donde `field(metadata=...)` no esté disponible. Es una tupla/lista/conjunto de nombres de campo
  leída de la **clase** (`is_field_not_traced` la comprueba antes que los metadatos de dataclass),
  así que las subclases la heredan y las instancias no pueden sobrescribirla.

Ambas ocultan de forma idéntica — campo por campo, no todo el objeto contenedor — y prevalecen
incondicionalmente sobre cualquier política:

```python
from dataclasses import dataclass

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    not_traced_field,
    trace_object,
)


@dataclass
class Credentials:
    username: str
    secret: str = not_traced_field(default="")


class LegacyCredentials:
    """A plain (non-dataclass) class: `__nt_not_traced__` names the fields to redact."""

    __nt_not_traced__ = ("secret",)

    def __init__(self, username: str, secret: str) -> None:
        self.username = username
        self.secret = secret


class AuthService:
    # Parameter named `account`, not `credentials` -- the latter is itself on the name-based
    # deny-list (see documentation/privacy-and-redaction.md) and would redact the whole argument
    # regardless of which fields inside it are marked `@not_traced`.
    def login(self, account: Credentials | LegacyCredentials) -> str:
        return f"session-for-{account.username}"


def run() -> str:
    """Traces two logins, one per redaction surface, and renders the result."""
    context = ContextVarNarrativeContext()
    service = trace_object(AuthService(), context)
    service.login(Credentials("alice", "hunter2"))
    service.login(LegacyCredentials("bob", "hunter2"))
    return IndentedTextRenderer().render(context.capture_trace())
```

`python -m examples.not_traced_fields` imprime (`0ms` varía según la máquina, igual que en la
página de 60 segundos):

```text
AuthService.login(account: Credentials(username="alice", secret=[REDACTED])) → "session-for-alice" — 0ms
AuthService.login(account: LegacyCredentials(username="bob", secret=[REDACTED])) → "session-for-bob" — 0ms
```

Los valores ocultos se sustituyen por un marcador antes del renderizado — nunca llegan a un
renderizador, un exportador ni a un log.

## El contrato de pureza — efectos secundarios durante el tracing

NarrativeTrace puede invocar un conjunto pequeño y fijo de rutas de código sobre tus objetos
mientras renderiza una traza. Mantén esos miembros **puros** — libres de efectos secundarios como
carga diferida, contadores de acceso, llenado de caché o E/S — igual que lo harías para un
depurador o un serializador.

Qué se invoca y qué no:

- **La introspección enumera datos almacenados, no código.** Los nombres de los campos provienen de
  `dataclasses.fields()`, los metadatos de attrs, el `_fields` de un `NamedTuple`, o el
  `__dict__`/`__slots__` de la instancia — por lo que una `@property` calculada (cuyo getter podría
  contar accesos o cargar de forma diferida) nunca se enumera ni se ejecuta durante la
  introspección. Un `NamedTuple` se introspecciona por nombre de campo en lugar de renderizarse
  como una lista anónima de valores posicionales, de modo que un campo oculto permanece oculto de
  la misma manera que un campo de dataclass.
- **Un `__str__` personalizado nunca es de confianza para tus propios tipos** *(since 0.1.2)*.
  Cualquier objeto que porte estado de instancia — una dataclass, una clase attrs, un `NamedTuple`,
  o un objeto plano con `__dict__`/`__slots__` poblado — se introspecciona campo por campo sin
  importar si además define `__str__`/`__repr__`; ese método escrito a mano nunca se consulta,
  igual que nunca se consultaba en una dataclass. Antes de esta corrección, el `__str__`
  personalizado de una clase plana prevalecía sobre la introspección sin más, así que un `__str__`
  escrito a mano que interpolara un campo sensible — directamente, o de forma transitiva a través
  del `__str__` de un objeto anidado — sorteaba la ocultación por completo; una clave de dict/map
  tenía la misma brecha exacta (un `str(key)` desnudo y sin mediar), ahora cerrada de la misma
  forma: una clave se introspecciona y se comprueba contra la ocultación exactamente igual que un
  valor. Dale a un compuesto un método `@narrative_summary` cuando quieras un resumen curado de una
  línea en lugar del predeterminado campo por campo — ese mecanismo no se ve afectado y sigue
  siendo la forma admitida de controlar exactamente qué se muestra.
- **No declarar ningún campo tampoco otorga confianza** *(since 0.1.3, unreleased)*. Un valor cuyo
  estado la introspección no puede ver — una subclase de `ctypes.Structure` o un tipo de extensión
  que guarda sus campos en una estructura C, una clase que guarda su estado en una tabla a nivel de
  módulo indexada por identidad o en un cierre — se contaba como hoja y se renderizaba mediante su
  propio `__str__`/`__repr__`, que podía imprimir esos campos superando la lista de denegación.
  Ahora se renderiza solo como el nombre de su tipo (`<CStructCredentials>`): presente, acotado, sin
  leer. Los propios tipos de valor de la biblioteca estándar (`pathlib.Path`, `datetime`,
  `uuid.UUID`, `decimal.Decimal`, un miembro de `Enum`, …) siguen renderizándose con su propio texto
  breve — esa confianza la decide el origen, y nada más.
- **Un resumen, `__str__` o getter que lanza excepción renderiza un marcador de error tipado,
  nunca su propio mensaje** *(since 0.1.2)*. `<error: ValueError>`, `<error: RecursionError>`, y así sucesivamente
  — el nombre del propio TIPO de la excepción de la parte que falla, sustituido solo para esa
  parte (nunca toda la traza, nunca un `<error>` desnudo). El *mensaje* de la excepción
  deliberadamente nunca se renderiza: un mensaje puede llevar el mismo valor que falló al
  renderizarse (`"summary failed for {token}"` filtraría `token` de otro modo), así que solo el
  nombre del tipo — nunca `str(exc)` — llega a la salida.
- **Una colección solo se enumera cuando está definida por la plataforma.** `list`/`tuple`/
  `dict`/`set`/`frozenset` se enumeran a través de su propio estado; una subclase de una de ellas
  se enumera a través de la propia lectura de estado de ese ancestro, nunca a través del
  `__iter__`/`items` sobrescrito de la subclase. Una colección hecha a mano (que implementa el
  protocolo `Collection` desde cero, sin ancestro de plataforma) tampoco se enumera — se
  renderiza como un objeto ordinario, campo por campo. Un iterable simple que no es un
  `Collection` completo (sin `__contains__`) se renderiza como su nombre de tipo más el tamaño,
  nunca sus elementos, y su `__iter__` nunca se toca. La única excepción es el gancho
  `__narrative_elements__` de abajo.
- **`__narrative_elements__` es el único gancho de confianza para enumerar sus propios
  elementos.** Definido con más detalle abajo.
- **La invocación está acotada y aislada.** La salida tiene un límite (longitud de cadena,
  elementos de colección, profundidad); un `__str__`, resumen o getter que lance una excepción
  nunca puede hacer fallar la llamada de negocio trazada (las plantillas recurren al marcador de
  posición literal `{placeholder}`); los valores se renderizan de forma eager en el punto de
  llamada, por lo que cualquier efecto secundario ocurre una sola vez, en un punto determinista.
  Los futures y los awaitables nunca se fuerzan.

## `__narrative_elements__` — iteración de confianza

El tercer gancho de renderizado sancionado, junto a `@narrative_summary` y el propio `__str__` de
un valor de la plataforma: un tipo que declara un método `__narrative_elements__` sin argumentos es de
confianza para enumerar sus propios elementos a través de ese método — el único caso en el que el
renderizado ejecuta la propia iteración de un tipo, porque quien lo escribió la declaró pura.

```python
class OrderLine:
    def __init__(self, items: list[Item]) -> None:
        self._items = items

    def __narrative_elements__(self) -> list[Item]:
        return list(self._items)
```

Un `OrderLine` renderizado muestra sus elementos (con el mismo límite de elementos que una
colección ordinaria, con el mismo marcador `… (N total)` al superarlo) en lugar del nombre de su
campo `_items`. El método se ejecuta bajo la misma protección reflectiva de renderizado que
cualquier otro gancho: una llamada que haga a un objeto trazado no abre ningún span propio. Un
`__narrative_elements__` que lanza excepción degrada al mismo marcador tipado `<error: TypeName>`
que cualquier otro fallo de gancho, nunca a los campos reales del objeto.

Úsalo cuando un tipo de colección hecho a mano (uno sin ancestro de plataforma al que recurrir, y
que por tanto se renderizaría como un objeto ordinario) tenga elementos que valga la pena mostrar
directamente — el mismo papel que cumple `@NarrativeElements` en el resto de los runtimes de
NarrativeTrace.

Si un miembro no puede ser puro, márcalo con `@not_traced` / `not_traced_field(...)` — el valor de
un miembro oculto nunca se lee en absoluto — o dale al tipo un `@narrative_summary` para que
controles exactamente qué se accede (un `__str__` curado ya no saca a un compuesto de la
introspección, ver arriba). Con `NARRATIVETRACE_LEVEL=OFF` (y, para los valores de los parámetros,
con `SUMMARY`), no se produce renderizado de argumentos en absoluto.
