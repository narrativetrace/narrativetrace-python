<!-- source: documentation/guides/logging.md blob e987a2d7cfb1 | translated: 2026-09-11 | reviewed: - -->

# Logging & structlog

O NarrativeTrace faz ponte com o framework `logging` da stdlib e com o `structlog`, emitindo as
*mesmas* chaves canônicas de correlação a partir de ambos.

## logging da stdlib

Duas peças:

- `LoggingTraceConsumer` — um consumidor de eventos que registra entrada/retorno em `DEBUG` e
  exceções em `WARNING` (`!! {type}: {message} [{error_context}]`, sanitizado contra caracteres de
  controle).
- `NarrativeContextFilter` — um `Filter` de logging que estampa as chaves do escopo atual (`traceId`,
  `traceName`, `spanId`, `nt.class`, `nt.method`, `nt.depth`, identidade do serviço, chaves de
  requisição/usuário) em todo registro.

```python
import logging
from narrativetrace import NarrativeContextFilter

handler = logging.StreamHandler()
handler.addFilter(NarrativeContextFilter())
logging.getLogger().addHandler(handler)
```

## Escopo em nível de requisição

Dentro de uma requisição HTTP, o middleware ASGI abre um `request_log_scope(...)` para que as chaves
da requisição (`httpMethod`, `httpRoute`, `clientIp`, identidade do usuário) acompanhem por baixo de
qualquer escopo de método ativo.

## structlog

`narrativetrace-structlog` fornece um processador que injeta o mesmo conjunto de chaves:

```python
import structlog
from narrativetrace_structlog import narrative_context_processor

structlog.configure(
    processors=[narrative_context_processor, structlog.processors.JSONRenderer()]
)
```

Os dois front-ends compartilham `narrativetrace.current_scope_keys()` como a única fonte de
vocabulário, então seus conjuntos de chaves nunca podem divergir.

## Onde isso está conectado nos exemplos

Todo exemplo executável em `examples/` envia seu trace para um logger configurado de forma
realista, ao lado da sua narração de console — `logging.basicConfig` na raiz de composição mais
`LoggingTraceConsumer`/`NarrativeContextFilter` desta guia, não um trecho copiado num README. Veja
[`examples/README.md`](../../examples/README.md#where-the-logger-is-configured) para saber qual
arquivo configura qual exemplo.
