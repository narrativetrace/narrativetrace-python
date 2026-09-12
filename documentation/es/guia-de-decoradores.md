<!-- source: documentation/guides/decorators.md blob 6f260cb42c31 | translated: 2026-09-12 | reviewed: - -->

# Guía de decoradores

Envolver un objeto con `trace_object` traza cada método público. Los decoradores refinan qué se
captura y cómo se lee.

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
- **Un `__str__` personalizado solo es de confianza para una hoja genuina** *(since 0.1.2,
  unreleased)*. Cualquier objeto que porte estado de instancia — una dataclass, una clase attrs, un `NamedTuple`,
  o un objeto plano con `__dict__`/`__slots__` poblado — se introspecciona campo por campo sin
  importar si además define `__str__`/`__repr__`; ese método escrito a mano nunca se consulta,
  igual que nunca se consultaba en una dataclass. Solo un valor sin ningún estado de instancia (un
  número, una cadena, una clase auxiliar sin estado, un miembro de `Enum` sin carga) sigue
  renderizándose mediante su propio `str()`. Antes de esta corrección, el `__str__` personalizado
  de una clase plana prevalecía sobre la introspección sin más, así que un `__str__` escrito a mano
  que interpolara un campo sensible — directamente, o de forma transitiva a través del `__str__` de
  un objeto anidado — sorteaba la ocultación por completo; una clave de dict/map tenía la misma
  brecha exacta (un `str(key)` desnudo y sin mediar), ahora cerrada de la misma forma: una clave se
  introspecciona y se comprueba contra la ocultación exactamente igual que un valor. Dale a un
  compuesto un método `@narrative_summary` cuando quieras un resumen curado de una línea en lugar
  del predeterminado campo por campo — ese mecanismo no se ve afectado y sigue siendo la forma
  admitida de controlar exactamente qué se muestra.
- **Un resumen, `__str__` o getter que lanza excepción renderiza un marcador de error tipado,
  nunca su propio mensaje** *(since 0.1.2, unreleased)*. `<error: ValueError>`, `<error: RecursionError>`, y así sucesivamente
  — el nombre del propio TIPO de la excepción de la parte que falla, sustituido solo para esa
  parte (nunca toda la traza, nunca un `<error>` desnudo). El *mensaje* de la excepción
  deliberadamente nunca se renderiza: un mensaje puede llevar el mismo valor que falló al
  renderizarse (`"summary failed for {token}"` filtraría `token` de otro modo), así que solo el
  nombre del tipo — nunca `str(exc)` — llega a la salida.
- **La invocación está acotada y aislada.** La salida tiene un límite (longitud de cadena,
  elementos de colección, profundidad); un `__str__`, resumen o getter que lance una excepción
  nunca puede hacer fallar la llamada de negocio trazada (las plantillas recurren al marcador de
  posición literal `{placeholder}`); los valores se renderizan de forma eager en el punto de
  llamada, por lo que cualquier efecto secundario ocurre una sola vez, en un punto determinista.
  Los futures y los awaitables nunca se fuerzan.

Si un miembro no puede ser puro, márcalo con `@not_traced` / `not_traced_field(...)` — el valor de
un miembro oculto nunca se lee en absoluto — o dale al tipo un `@narrative_summary` para que
controles exactamente qué se accede (un `__str__` curado ya no saca a un compuesto de la
introspección, ver arriba). Con `NARRATIVETRACE_LEVEL=OFF` (y, para los valores de los parámetros,
con `SUMMARY`), no se produce renderizado de argumentos en absoluto.
