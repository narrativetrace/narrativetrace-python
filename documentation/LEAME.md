# Documentación de NarrativeTrace

[English](README.md) | **Español** | [Português](LEIAME.md) | [简体中文](自述文件.md)

El índice de los documentos de usuario de este repositorio, en español. Cada documento aquí
listado es una traducción derivada de su fuente en inglés — ver
[`i18n/manifest.json`](i18n/manifest.json) para el conjunto de idiomas declarado y el estado de
cada traducción. Los documentos solo de ingeniería (registros de ADR, notas de pruebas de
seguridad/concurrencia, notas de diseño con fecha) son solo en inglés por convención y no forman
parte del conjunto traducido de ningún idioma — consulta el [índice en inglés](README.md) para
verlos.

## Primeros pasos

| Documento | Qué cubre |
|---|---|
| [Ve una traza en 60 segundos](es/sesenta-segundos.md) | Un servicio diminuto, salida real, desde la instalación hasta un valor ocultado |
| [Eligiendo una integración](es/eligiendo-una-integracion.md) | Qué paquete necesitas, como diagrama de decisión |
| [Guía de instalación](es/guia-de-instalacion.md) | Cada paquete, qué añade |
| [Guía de configuración](es/guia-de-configuracion.md) | Niveles de tracing, configuración de la salida, cadena de precedencia |
| [Guía de decoradores](es/guia-de-decoradores.md) | `@narrated`, `@on_error`, `@not_traced`, el contrato de pureza |
| [Privacidad y ocultación](es/privacidad-y-ocultacion.md) | El contrato de ocultación fila por fila, verificado contra el código |
| [Qué commitear](es/que-commitear.md) | Qué archivos generados son artefactos de CI, y cuáles (si los hay) son líneas base revisadas |
| [Formato de traza estructural](es/formato-de-traza-estructural.md) | El artefacto `.nt` libre de valores: gramática, nombrado por invocación, línea base en verde, modo de aprobación |
| [Habilidades del agente](es/habilidades-del-agente.md) | `narrativetrace-doctor` y `add-narrative-tracing` — procedimientos cargables por un agente sobre la CLI probada |
| [Usa NarrativeTrace con tu agente](es/usa-narrativetrace-con-tu-agente.md) | Por plataforma — Cursor, Replit, Antigravity, GitHub Copilot, Claude Code — cómo llegan las habilidades a un proyecto, qué archivo de aviso escribe `init` y qué encuentra el agente |
| [Solución de problemas](es/solucion-de-problemas.md) | Síntoma → causa → arreglo para los fallos que la gente realmente encuentra |

## Recetas

Una página por problema, con las palabras que escribiría un usuario — cada una incluye el código de su escenario y la salida real de una ejecución que esta build realiza.

| Documento | Qué cubre |
|---|---|
| [Añade registro a este servicio](es/anade-registro-a-este-servicio.md) | Un checkout sin ninguna sentencia de log: envuelve sus colaboradores una vez y cada llamada aparece en tu propia salida de `logging` |
| [Ayúdame a depurar y arreglar este error](es/ayudame-a-depurar-y-arreglar-este-error.md) | Una tarjeta rechazada deja el stock reservado: la narrativa que falla, el arreglo y la traza aprobada que lo fija |
| [Por qué falló esta prueba](es/por-que-fallo-esta-prueba.md) | Una prueba en rojo leída span por span contra su aserción — aquí lo desactualizado es la expectativa |
| [Revisa un flujo complejo antes de cambiarlo](es/revisa-un-flujo-complejo-antes-de-cambiarlo.md) | Una ejecución en `DETAIL` y en `SUMMARY`, la línea de log junto al `.nt` libre de valores |
| [Revisa una refactorización: ¿cambió el comportamiento?](es/revisa-una-refactorizacion-cambio-el-comportamiento.md) | Las pruebas siguen en verde, el diff de aprobación nombra la llamada eliminada |

## Integraciones

| Documento | Qué cubre |
|---|---|
| [Guía de pytest](es/guia-de-pytest.md) | El fixture `narrative_trace`, artefactos por prueba, el pie de claridad |
| [Guía de FastAPI / ASGI](es/guia-de-fastapi-asgi.md) | Middleware de Starlette/FastAPI, traceparent W3C, el accesor de la petición |
| [Guía de OpenTelemetry](es/guia-de-opentelemetry.md) | El puente de spans de OTel: listener en vivo y exportador por lotes |
| [Guía de logging](es/guia-de-logging.md) | El puente de logging de la stdlib y el procesador de structlog |

## Análisis y salida

| Documento | Qué cubre |
|---|---|
| [Guía de claridad](es/guia-de-claridad.md) | El modelo de puntuación, la integración equivalente a JUnit, y la puerta estilo `clarityCheck` |
| [Guía de funcionalidades](es/guia-de-funcionalidades.md) | El catálogo canónico: cada funcionalidad, su nivel, su estado |

## Manteniendo este índice honesto

Añadir o quitar una traducción bajo `documentation/es/` significa actualizar este archivo y
`documentation/i18n/manifest.json` en el mismo cambio. Un documento que no aparece aquí es
invisible para quien navegue el repositorio en español.
