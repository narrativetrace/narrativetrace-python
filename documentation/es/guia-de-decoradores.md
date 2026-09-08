<!-- source: documentation/guides/decorators.md blob 9efb34f63ba8 | translated: 2026-09-07 | reviewed: - -->

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

Oculta un parámetro por nombre, o un campo mediante un atributo de clase o metadatos de dataclass:

```python
from dataclasses import dataclass, field
from narrativetrace import not_traced, not_traced_field

class AuthService:
    @not_traced("password")
    def login(self, username: str, password: str) -> Session:
        ...

@dataclass
class Credentials:
    username: str
    secret: str = not_traced_field(default="")   # o: __nt_not_traced__ = ("secret",)
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
  `dataclasses.fields()`, los metadatos de attrs, el `_fields` de un `NamedTuple`, o el `__dict__`
  de la instancia — por lo que una `@property` calculada (cuyo getter podría contar accesos o
  cargar de forma diferida) nunca se enumera ni se ejecuta durante la introspección. Un
  `NamedTuple` se introspecciona por nombre de campo en lugar de renderizarse como una lista
  anónima de valores posicionales, de modo que un campo oculto permanece oculto de la misma manera
  que un campo de dataclass.
- **Lo que NarrativeTrace sí invoca:** un `__str__` personalizado, un método `@narrative_summary`,
  y cualquier ruta de propiedad que nombres en una plantilla `@narrated`/`@on_error` —
  `{order.total}` se resuelve mediante `getattr`, por lo que una `@property` nombrada allí *sí*
  ejecutará su getter.
- **La invocación está acotada y aislada.** La salida tiene un límite (longitud de cadena,
  elementos de colección, profundidad); un `__str__` o getter que lance una excepción nunca puede
  hacer fallar la llamada de negocio trazada (las plantillas recurren al marcador de posición
  literal `{placeholder}`); los valores se renderizan de forma eager en el punto de llamada, por lo
  que cualquier efecto secundario ocurre una sola vez, en un punto determinista. Los futures y los
  awaitables nunca se fuerzan.

Si un miembro no puede ser puro, márcalo con `@not_traced` / `not_traced_field(...)` — el valor de
un miembro oculto nunca se lee en absoluto — o dale al tipo un `__str__` / `@narrative_summary`
curado para que controles exactamente qué se accede. Con `NARRATIVETRACE_LEVEL=OFF` (y, para los
valores de los parámetros, con `SUMMARY`), no se produce renderizado de argumentos en absoluto.
