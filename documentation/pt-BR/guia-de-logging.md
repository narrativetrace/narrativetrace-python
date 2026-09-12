<!-- source: documentation/guides/logging.md blob f101581900b6 | translated: 2026-09-12 | reviewed: - -->

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

## Um consumidor por stream, vários handlers

`nt.depth` é um contador privado de cada instância de `LoggingTraceConsumer` *(since 0.1.2,
unreleased)*, então duas delas
reproduzindo o *mesmo* stream de eventos (digamos, ambas conectadas como listeners num mesmo
pipeline) reportam cada uma a sua própria profundidade correta — uma não corrompe mais a
contagem da outra. O `NarrativeContextFilter` e o processador do `structlog` não são afetados de
forma alguma: eles leem a identidade compartilhada de classe/método/trace do frame mais interno,
que é a mesma para qualquer instância que processe um evento, nunca o contador de profundidade
próprio de um consumidor. Ainda assim, prefira um único `LoggingTraceConsumer` por stream de
eventos — é mais fácil de raciocinar, e uma segunda instância perdida é fácil de criar por
acidente (por exemplo, dois pedaços diferentes de código de configuração criando cada um a sua).
Quer o trace em mais de um lugar (stdout e um arquivo, digamos)? Adicione mais `logging.Handler`s
ao seu logger em vez de um segundo consumidor:

```python
logger = logging.getLogger("narrativetrace")
logger.addHandler(logging.StreamHandler())           # first destination
logger.addHandler(logging.FileHandler("trace.log"))  # second destination, same consumer
```

## `export_to_logger` — uma única chamada

*(since 0.1.2, unreleased)* — na versão publicada no PyPI, `0.1.1`, reproduza
`store.events()` através de um `LoggingTraceConsumer` na mão em vez disso.

`export_to_logger(trace, logger=None)` reproduz um trace já capturado através de um
`LoggingTraceConsumer` privado em uma única chamada — sem `EventStore` para conectar na mão, sem
loop para escrever:

```python
from narrativetrace import ContextVarNarrativeContext, export_to_logger, trace_object

context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

export_to_logger(context.capture_trace())
```

Cada chamada abre seu próprio consumidor privado, então chamá-la mais de uma vez — mesmo
concorrentemente, a partir de threads diferentes — nunca viola a regra de "um consumidor por
stream" acima.

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
