<!-- source: documentation/privacy-and-redaction.md blob 595bbfcedfbf | translated: 2026-09-07 | reviewed: - -->

# Privacidad y ocultación

Esta librería corre dentro de tu proceso y escribe archivos que tu equipo va a compartir — artefactos
de CI, líneas de log de producción. Esta página es la versión fila por fila de ese contrato: qué
oculta, hasta dónde llega y hasta dónde no, y qué garantiza NarrativeTrace frente a lo que no promete
en absoluto. Verificado directamente contra `packages/narrativetrace/src/narrativetrace/redaction.py`
y `template.py`, no inferido de otra documentación.

## Ocultación, superficie por superficie

| Superficie | ¿Se puede desactivar la ocultación integrada? |
|---|---|
| Salida del plugin de pytest | No |
| Middleware ASGI (exportación de metadatos de petición/usuario) | No |
| Puente de OpenTelemetry | No |
| Procesador de structlog / puente de logging de la stdlib | No |
| Un `ValueRenderer` personalizado que construya tu propio código | Sí — solo pasando `RedactionPolicy.DISABLED` a `trace_object(obj, context, renderer=ValueRenderer(redaction_policy=RedactionPolicy.DISABLED))` explícitamente |
| `@not_traced` / `not_traced_field(...)` | No aplica — es lo que provoca la ocultación, y siempre gana |

Cada integración distribuida renderiza valores mediante el mismo mecanismo `ValueRenderer`/
`RedactionPolicy` que usa `trace_object` por defecto (`RedactionPolicy.DEFAULT`) — ninguna expone un
flag de configuración, variable de entorno o ajuste de plugin que llegue a `DISABLED`. La única forma
de llegar ahí es código de aplicación que construye su propio `ValueRenderer` y lo pasa explícitamente
— un acto deliberado y revisable en tu propio código fuente, no un estado que un deploy pueda cambiar
en silencio.

## Qué atrapa la lista de denegación, y qué la supera

Dos mecanismos de ocultación independientes se aplican a cada valor renderizado por reflexión:

1. **`@not_traced("param")` / `not_traced_field(...)` / `__nt_not_traced__`** — siempre oculta,
   incondicionalmente, sin importar la política.
2. **La lista de denegación basada en nombre** (`RedactionPolicy.DEFAULT`) — una coincidencia de
   subcadena sin distinguir mayúsculas/minúsculas ni acentos contra nombres de campo/parámetro,
   **multilingüe y siempre activa, sin configuración regional que elegir**: el inglés (`password`,
   `secret`, `token`, `cvv`, `ssn`, `apikey`, `cardnumber`, `sessionid`, y más) convive con
   palabras en español, portugués, francés y chino (`contraseña`, `senha`, `motDePasse`, `密码`, y
   más) — `pan`/`iban` y ocho palabras no inglesas coinciden en los límites del token del
   identificador en lugar de como subcadenas sin más, específicamente para que `companyName` o
   `japaneseAddress` no queden atrapados sin querer — más una segunda comprobación independiente
   sobre la *forma* del propio valor: un JWT, una cadena `Set-Cookie`, una secuencia de dígitos
   con forma de número de tarjeta, o un número de identidad nacional (RUT chileno, CPF/CNPJ
   brasileño, DNI/NIE español, NIR francés, cédula de identidad china) que supera su propia suma
   de verificación — de modo que un token bearer o un número de identidad pasado bajo un nombre no
   reconocido se sigue atrapando.

Un `NamedTuple` se introspecciona por nombre de campo en lugar de renderizarse como una tupla
posicional anónima, así que un campo oculto dentro de uno permanece oculto igual que un campo de
dataclass — la ocultación sobrevive ese nivel de contenedor. Y gana sobre una plantilla de narración
que lo nombra: `{param.property}` en `@narrated`/`@on_error` resuelve una ruta hacia un miembro
oculto como `[REDACTED]`, en cada nivel de la ruta, nunca con el valor literal.

**Una limitación documentada, registrada en lugar de corregida.** La resolución de marcadores de
posición de plantilla (`{param}`, `{param.property}`) siempre comprueba los valores contra
`RedactionPolicy.DEFAULT` — la política no se propaga desde un `ValueRenderer` personalizado que
pases a `trace_object`. En la práctica esto solo importa si además construyes una política
personalizada o deshabilitada: el renderizado normal de parámetros y valores de retorno respeta esa
política personalizada, pero una plantilla `@narrated`/`@on_error` que resuelve el mismo valor sigue
comprobando debajo la lista de denegación por defecto. `@not_traced` no se ve afectado — siempre
oculta sin importar qué política esté en vigor.

Detalle completo y ejemplos trabajados: [Guía de decoradores](guia-de-decoradores.md).

## Garantías

- **Los fallos de tracing están aislados de la ejecución del host.** El registro está aislado de
  excepciones en cada vía; un `__str__` que lanza excepción, un buffer lleno o un handler de log roto
  nunca cambian lo que tu método devuelve o lanza.
- **La salida no se puede falsificar.** Los valores renderizados, los mensajes de excepción y el
  texto de narración pasan por un escapado de caracteres de control y de sustitutos (surrogates)
  antes de llegar a una línea de log, un renderizador de consola o un documento Markdown — así que un
  valor no puede inyectar una línea de log falsa ni romper el formato del artefacto.
- **La vía de análisis en buffer puede descartar eventos, pero siempre informa de la pérdida.** Es un
  anillo de tamaño fijo (65.536 ranuras por defecto — el parámetro del constructor `buffer_capacity`
  de `BufferedEventConsumer`, para código que construye su propio pipeline) que sobrescribe el evento
  más antiguo bajo carga sostenida en lugar de crecer sin límite o bloquear al llamador; una ejecución
  que perdió eventos imprime el recuento en su propia línea de pie de página `Incomplete:` de la suite
  en lugar de subinformar en silencio.
- **La introspección lee datos almacenados, no código.** Los nombres de campo provienen de
  `dataclasses.fields()`, los metadatos de attrs, el `_fields` de un `NamedTuple`, o el `__dict__` de
  la instancia — un getter `@property` calculado nunca se enumera ni se ejecuta durante la
  introspección.

## No garantías

- **Ninguna promesa de "coste cero".** El tracing hace trabajo, y el trabajo cuesta algo — consulta
  la [sección de rendimiento del LEAME](../../LEAME.md).
- **Ningún tracing de métodos privados.** `trace_object` solo intercepta el acceso a atributos
  públicos (`__getattr__`); un nombre que empieza con `_` nunca se envuelve, y los métodos dunder
  (`__str__`, `__eq__`, …) se resuelven sobre el tipo y tampoco llegan nunca al wrapper — así que
  `str()`/`repr()`/`==`/`isinstance()` sobre un objeto envuelto dejan de reflejar en silencio el
  objeto original, sin marcador ni API de desenvuelto para detectar el envoltorio desde fuera.
- **Ningún tracing automático de un objeto que no hayas envuelto explícitamente.** No hay import
  hook, ni instrumentación de bytecode, ni auto-wrap a nivel de framework disponible hoy — consulta
  [Eligiendo una integración](eligiendo-una-integracion.md).
- **La ocultación se basa en nombre y forma, no en un análisis de flujo de datos.** Un valor sensible
  almacenado bajo un nombre que la lista de denegación no reconoce, y que no coincide con ninguna
  forma de secreto conocida, no se oculta a menos que lo marques explícitamente.

## El modelo de pérdida en producción, visualmente

Las dos mitades del pipeline de doble vía (registro de decisión de producto PY-002) llevan
obligaciones opuestas por diseño:

```text
vía de log síncrona (logging de la stdlib, en línea en el hilo del llamador)
   no debe hacer fallar la aplicación host
   durable — este es el registro

vía de análisis en buffer (anillo acotado, drenado por un hilo en segundo plano)
   puede descartar eventos bajo carga, y siempre lo dice
   nunca debe bloquear al llamador
   nunca debe crecer más allá de su límite (65.536 ranuras por defecto)
   de mejor esfuerzo — esto es análisis, no auditoría
```

Perder el buffer pierde fidelidad de análisis — árboles de trazas capturados, puntuación de claridad,
spans de OTel — para los eventos descartados durante esa ventana. Perder el flujo de log pierde el
registro. Esa asimetría es la razón de que sean dos vías con dos comportamientos de fallo distintos,
en lugar de una sola vía con una única contrapartida.

## Lo que esta página no cubre

Qué ocurre cuando NarrativeTrace se apila con proxies al estilo AOP, librerías de contratos, u otra
herramienta que envuelve los mismos objetos sigue dos invariantes — un solo frame de traza por
cruce de frontera de negocio, y ningún resultado que dependa del orden de los wrappers — cubiertos
en la [sección de privacidad y seguridad del LEAME](../../LEAME.md#privacidad-y-seguridad). Cada
nivel de tracing y cada ajuste de formato de salida, incluido cómo `NARRATIVETRACE_LEVEL` controla la
captura antes de que ocurra cualquier renderizado, está en la
[Guía de configuración](guia-de-configuracion.md).
