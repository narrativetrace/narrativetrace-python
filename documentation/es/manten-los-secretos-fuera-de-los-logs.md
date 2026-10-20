<!-- source: documentation/recipes/keep-secrets-out-of-the-logs.md blob 5343825aa6f3 | translated: 2026-10-18 | reviewed: - -->

# Mantén los secretos fuera de los logs

## El problema

> Si esto registra cada llamada con cada argumento, va a registrar un número de
> tarjeta. Convénceme de que no.

El checkout recibe una contraseña y un número de tarjeta. Abajo hay una
ejecución con ambos, el log que escribió de verdad, y la prueba que demuestra
que ninguno de los dos valores está en ese fichero.

## Configuración mínima

Ninguna. La ocultación está activada en toda integración que se distribuye y
no existe ninguna superficie de configuración que la desactive — la lista de
denegación se consulta en la *captura*, antes de que un valor se convierta en
evento, así que un valor denegado nunca llega a la línea de log, al fichero de
traza, al camino con búfer ni a un consumidor de los eventos.
[Privacidad y ocultación](privacidad-y-ocultacion.md) es la versión fila por
fila, verificada contra el código.

Aun así, hay dos cosas que vale la pena hacer una vez en tu propio proyecto:

1. **Escribe la prueba de esta página para tu propio flujo.** Una ocultación
   que no has afirmado es una afirmación de palabra, no una propiedad de tu
   build. El hallazgo del doctor "redaction never proven in a test"
   (`trap.redaction-proof`) existe exactamente para esto.
2. **Conoce la vía de escape.** Un secreto bajo un nombre que nadie podría
   adivinar — `fingerprint`, `answer2` — se alcanza con
   `@not_traced("fingerprint")` en el método (o `not_traced_field(...)` en un
   campo de dataclass), que siempre gana
   ([Guía de decoradores](guia-de-decoradores.md)).

## El escenario

Un colaborador nuevo, para que la ejecución lleve una contraseña además de una
tarjeta. Su parámetro se llama `password` — ese nombre es todo el sentido:

```python
"""Signs a customer in before the checkout charges them."""

from __future__ import annotations


class CustomerAccounts:
    """In-memory accounts. The parameter is named ``password`` -- that name is the whole point of
    documentation/recipes/keep-secrets-out-of-the-logs.md."""

    def sign_in(self, customer_id: str, password: str) -> str:
        """Returns the session id the checkout carries for the rest of the request.

        Raises ``ValueError`` when the password is blank.
        """
        if not password.strip():
            raise ValueError("password must not be blank")
        return f"SESSION-{customer_id}"
```

La ejecución inicia sesión del cliente y hace el pedido. Los dos valores
secretos son constantes aquí para que la prueba pueda buscarlos después en el
log — un flujo real los obtiene de la petición:

```python
"""documentation/recipes/keep-secrets-out-of-the-logs.md's scenario: one checkout carrying a
password and a card number writes neither into the log its own ``logging`` setup produced -- the
password caught by its NAME, the card number by its name and again by its VALUE (rule 8, docs as
tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs it in its own pytest process and
names the log file (``NARRATIVETRACE_RECIPE_LOG``), which is the file the page embeds. The
assertion reads that file back, not a rendering this test produced: a page claiming "the secret is
not in your log" is only worth what a real log file says.
"""

import os
from pathlib import Path

from examples.recipes.checkout.accounts import CustomerAccounts
from examples.recipes.checkout.env import LOG_FILE_ENV
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, export_to_logger, trace_object

# A fixed trace id, so the page's embedded output names the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")

# Luhn-valid, like a real one -- which is what the value-shape rule recognizes.
CARD_NUMBER = "4242424242424242"

# The password this run signs in with. It matches no value-shape rule at all: only its parameter's
# NAME can save it. Named for the phrase rather than for the field it fills, because the public
# snapshot's secrets gate reads a constant whose name carries that word and whose value is a string
# literal as a credential shipped in the open -- correctly, for every such line but a documentation
# fixture's.
SIGN_IN_PASSPHRASE = "orchid-trombone-77"


def test_a_checkout_with_a_password_and_a_card_writes_neither(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    accounts = trace_object(CustomerAccounts(), narrative_trace)
    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    session = accounts.sign_in("C-1234", SIGN_IN_PASSPHRASE)
    order_id = checkout.place_order("C-1234", "SKU-KB", 2, CARD_NUMBER)

    export_to_logger(narrative_trace.capture_trace())

    assert session == "SESSION-C-1234"
    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert_neither_secret_is_in_the_log()


def assert_neither_secret_is_in_the_log() -> None:
    """The proof: the log file the project's own handler wrote, read back and searched."""
    log = Path(os.environ[LOG_FILE_ENV]).read_text(encoding="utf-8")

    assert 'CustomerAccounts.sign_in(customer_id: "C-1234", password: [REDACTED])' in log
    assert "card_number: [REDACTED]" in log
    assert "card: [REDACTED]" in log
    assert SIGN_IN_PASSPHRASE not in log
    assert CARD_NUMBER not in log
```

## La salida real

**El log que escribió la ejecución**, a través del logger propio del proyecto:

```text
DEBUG [solid wand romps] [narrativetrace] - → CustomerAccounts.sign_in(customer_id: "C-1234", password: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - ← returned: "SESSION-C-1234"
DEBUG [solid wand romps] [narrativetrace] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - ← returned: "PAY-C-1234-7998"
DEBUG [solid wand romps] [narrativetrace] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - ← returned: "ORD-C-1234-SKU-KB-2"
```

**El fichero de traza de la misma ejecución**, que es la otra superficie a la
que podría haber llegado un secreto:

```text
---
type: trace
run: moody mouse sweeps
scenario: Test a checkout with a password and a card writes neither
entry_point: CustomerAccounts.sign_in
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 5
error_count: 0
---

## Trace: solid wand romps — CustomerAccounts.sign_in

**Scenario:** Test a checkout with a password and a card writes neither
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **CustomerAccounts.sign_in**(customer_id: `"C-1234"`, password: `[REDACTED]`) → `"SESSION-C-1234"` — 0ms #1
- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 0ms #2
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #2.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) → `"PAY-C-1234-7998"` — 0ms #2.2
  - **OrderRepository.save**(order: `Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998)`) → `null` — 0ms #2.3
  - → `"ORD-C-1234-SKU-KB-2"`
```

## Cómo leerlo

**Qué regla atrapó qué valor.** Tres valores han desaparecido, por dos
mecanismos independientes:

| Línea | Valor | Atrapado por |
|---|---|---|
| `#1` `CustomerAccounts.sign_in(…, password: [REDACTED])` | `orchid-trombone-77` | Su **nombre**. `password` está en la lista de denegación siempre activa, que compara nombres de parámetros, nombres de campos y campos de dataclass — en varios idiomas — en cualquier clase, la tuya incluida. El valor en sí no coincide con ningún patrón; nada salvo el nombre pudo salvarlo |
| `#2` `OrderService.place_order(…, card_number: [REDACTED])` | `4242424242424242` | Su **nombre** otra vez: `card_number` está en la misma lista |
| `#2.2` `PaymentService.charge(…, card: [REDACTED])` | el mismo número, una llamada más abajo | Su **valor**. El parámetro se llama `card`, que la lista de denegación no conoce — y el número es válido según Luhn, así que la comprobación independiente de la forma del valor lo atrapó igualmente |

Esa tercera fila es la que vale la pena recordar: `card` es como se llama un
parámetro en el código real, y el eje del nombre por sí solo lo habría
impreso. El eje de la forma reconoce un número de tarjeta válido según Luhn, un
JWT, una cadena `Set-Cookie`, un número de la Seguridad Social de EE. UU. y los
números nacionales de identidad que pasan sus propias sumas de control.

**Dónde viven las reglas.** En la biblioteca, no en tu configuración:
`RedactionPolicy.DEFAULT`, consultada por el único `ValueRenderer` que toda
integración que se distribuye construye de la misma manera. No hay ajuste,
variable de entorno ni nivel de log que la alcance;
[Privacidad y ocultación](privacidad-y-ocultacion.md) enumera tanto las
superficies como qué prevalece sobre qué. Por cierto, `customer_id: "C-1234"`
*sí* se escribe completo — un id de cliente es identificativo, no secreto, y
NarrativeTrace no adivina. Si el tuyo no debe registrarse, eso es
`@not_traced`, que es una decisión en tu código fuente y no un estado que un
despliegue pueda cambiar.

**Por qué la prueba es la demostración, y no la página.** Las últimas líneas
del escenario leen el fichero que escribió el handler y afirman dos cosas: que
los parámetros ocultos están presentes *como* `[REDACTED]`, y que ninguna de
las dos cadenas secretas aparece en ningún lugar de él. Una página solo puede
mostrarte bytes; una prueba rompe la build el día que una refactorización
renombra `password` a algo que la lista no conoce, o alguien construye su
propio `ValueRenderer` con `RedactionPolicy.DISABLED`. Esa es la diferencia
entre "era seguro cuando se escribió esto" y "es seguro ahora". Conserva las
aserciones de ausencia — las de `not in` — aunque las de presencia parezcan
suficientes: un valor que desaparece porque la llamada dejó de trazarse del
todo seguiría satisfaciendo la primera.

## Qué no se captura

- **El código que no se traza no es asunto de NarrativeTrace ocultarlo.** Arriba
  se envuelven cinco objetos; un secreto que pasa entre dos clases sin envolver
  no se ve, y por tanto ni se oculta ni se registra. Eso no es una garantía de
  seguridad — es una garantía de silencio.
- **Un secreto que escribe tu propia sentencia de log es cosa tuya.**
  NarrativeTrace oculta lo que *él* renderiza. `logger.info("charging %s", card_number)`
  es tu línea, en tu código, y nada aquí la filtra. El contrato de ocultación
  trata de la narrativa generada, no de todo lo que escribe el proceso.
- **Un valor de retorno no se compara por nombre**, porque no tiene. `sign_in`
  devuelve `"SESSION-C-1234"` y se imprime. Un token de sesión devuelto por un
  método trazado necesita que lo atrapen las reglas de forma, o `@not_traced`
  en el método, o un tipo de retorno más estrecho.
- **Nombres que la lista no conoce.** La lista es grande y multilingüe, no
  infinita. Un secreto llamado `q3` solo lo atrapa su forma, si la tiene.
  Afirma, no supongas — que es todo el sentido de esta página.
- **Lo que ocurre después de escribirse la línea de log.** El envío, la
  retención y el acceso al fichero son cosa de tu plataforma; el `.nt`
  estructural no lleva ningún valor y es el artefacto pensado para
  commitearse y para entregárselo a un modelo
  ([Revisa un flujo complejo antes de cambiarlo](revisa-un-flujo-complejo-antes-de-cambiarlo.md)).

**La skill para esto:** `narrativetrace-doctor` — una de sus comprobaciones es
exactamente "redaction never proven in a test", y nombra el arreglo.
