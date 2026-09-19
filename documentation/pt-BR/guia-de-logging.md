<!-- source: documentation/guides/logging.md blob 8e11e0235925 | translated: 2026-09-17 | reviewed: - -->

# Logging, structlog & Loguru

O NarrativeTrace faz ponte com o framework `logging` da stdlib e com o `structlog`, emitindo as
*mesmas* chaves canônicas de correlação a partir de ambos. Um usuário do Loguru chega ao mesmo
trace através da interoperabilidade com a stdlib que o próprio Loguru já documenta — veja
[Loguru](#loguru) mais abaixo.

## logging da stdlib

Duas peças:

- `LoggingTraceConsumer` — um consumidor de eventos que registra entrada/retorno em `DEBUG` e
  exceções em `WARNING` (`!! {type}: {message} [{error_context}]`, sanitizado contra caracteres de
  controle).
- `NarrativeContextFilter` — um `Filter` de logging que estampa as chaves do escopo atual (`traceId`,
  `traceName`, `spanId`, `nt.class`, `nt.method`, `nt.depth`, identidade do serviço, chaves de
  requisição/usuário) em todo registro. `traceName` e `runName` *(since 0.1.2)* estão
  sempre presentes uma vez que o filtro tocou um registro — `""` quando não há trace/execução
  ativos — então um padrão que referencia qualquer uma das duas nunca levanta exceção numa linha
  sem trace.

```python
import logging
from narrativetrace import NarrativeContextFilter

handler = logging.StreamHandler()
handler.addFilter(NarrativeContextFilter())
logging.getLogger().addHandler(handler)
```

## Um consumidor por stream, vários handlers

`nt.depth` é um contador privado de cada instância de `LoggingTraceConsumer` *(since 0.1.2)*, então duas delas
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

*(since 0.1.2)* — na versão publicada no PyPI, `0.1.1`, reproduza
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

## A execução tem sua própria chave MDC: `runName`

*(since 0.1.2)* O hook `pytest_sessionstart` do `narrativetrace-pytest` gera um id de
execução por sessão do pytest — nunca re-derivado — e chama `set_run_name(run.name)` para que
`runName` (a frase própria de três palavras da execução, distinta da `traceName` de qualquer
trace) acompanhe toda linha de log durante a sessão inteira, do mesmo jeito que
`request_log_scope` acompanha por baixo de um escopo de método; o hook `pytest_sessionfinish`
correspondente a limpa de novo. Um padrão mostrando as duas chaves:

```python
import logging

logging.basicConfig(format="%(asctime)s [%(traceName)s] [%(runName)s] %(message)s")
```

`runName` é `""` fora de uma sessão do pytest rastreada — um script simples, ou `export_to_logger`
chamado a partir de um — então o mesmo padrão é seguro em todo lugar. Veja [Guia de configuração,
§ A execução tem um nome](guia-de-configuracao.md#a-execução-tem-um-nome) para onde mais o nome
da execução aparece (o rodapé da suíte, `manifest.json`, o frontmatter de todo documento Markdown
de trace) e seu invariante: ele nunca chega ao artefato estrutural `.nt`.

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

## Loguru

O NarrativeTrace não traz nenhuma ponte específica para o Loguru — o Loguru é um logger, não uma
fonte de narração, e a ponte com a stdlib acima é todo o mecanismo que um usuário do Loguru
precisa. O Loguru documenta sua própria interoperabilidade com o `logging` da stdlib: um
`InterceptHandler` que herda de `logging.Handler` e reloga cada registro da stdlib através do
`logger` (veja a própria receita do Loguru, ["Entirely compatible with standard
logging"](https://loguru.readthedocs.io/en/stable/overview.html)). Aponte o logger raiz da stdlib
para esse handler, e o `export_to_logger` — a mesma reprodução de uma única chamada do [passo
"Envie para o seu logger" do tutorial de 60
segundos](sessenta-segundos.md#envie-para-o-seu-logger) — chega ao seu sink do Loguru sem
nenhum código específico do NarrativeTrace:

```python
# main.py
import inspect  # novo: o próprio percurso de frames do InterceptHandler, igual à receita do Loguru
import logging  # novo: o logger da stdlib do qual InterceptHandler herda; destino do export_to_logger
import sys  # novo: destino stdout para o sink abaixo

from loguru import logger  # novo: o sink de destino

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    TraceId,
    export_to_logger,  # novo: reproduz um trace já capturado no seu logger, em uma chamada
    trace_object,
)


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


# Um id de trace fixo, adotado para que a saída incorporada desta página sempre nomeie o mesmo
# trace. Uma execução real gera um aleatório a cada vez (nunca este — é a constante própria desta
# DEMO, não o padrão da biblioteca) pelo mesmo TraceId.adopt_trace_id que uma fronteira ao estilo
# servlet usa para um cabeçalho de trace de entrada.
DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")


# novo: a receita de interoperabilidade com a stdlib que o próprio Loguru documenta, ao pé da
# letra -- veja https://loguru.readthedocs.io/en/stable/overview.html, "Entirely compatible with
# standard logging". O NarrativeTrace não traz nenhuma ponte própria para o Loguru; essa receita
# é todo o mecanismo -- todo registro que um logger da stdlib emite (inclusive os do
# export_to_logger) é relogado através do `logger`.
class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Obtém o nível correspondente do Loguru, se existir.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Encontra quem chamou, a partir de onde a mensagem registrada se originou.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# novo: um sink fixo, sem timestamp, para que a saída incorporada desta página nunca varie
# conforme o relógio -- o seu próprio sink mantém o formato, as cores e a rotação reais; só esta
# demo precisa de determinismo.
logger.remove()
logger.add(sys.stdout, format="{level} | {message}", colorize=False)
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

trace = context.capture_trace()  # novo: captura uma vez, reutilizado pelo print e pelo export
print(IndentedTextRenderer().render(trace))

export_to_logger(trace)  # novo: o mesmo export de uma chamada do passo anterior -- agora no Loguru
```

```bash
uv run main.py
```

```text
trace: loose hook parks (a1b2c3d)

OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
DEBUG | → OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
DEBUG | ← returned: "ORD-cust-1-prod-42-3"
```

(o formato `"{level} | {message}"` do sink desta demo é uma escolha desta página, para uma saída
que nunca varia conforme o relógio; o seu sink real mantém o formato, as cores e a rotação que
você já configurou.) Um usuário do Loguru mantém tudo o que o Loguru já oferece — sinks, rotação,
cores, `logger.catch` — completamente intacto; o `export_to_logger` só reproduz um trace já
capturado através da ponte com a stdlib que o `InterceptHandler` do Loguru já está ouvindo. O que
ele deixa de escrever é a chamada a `logger.info(...)` (ou `logger.debug(...)`) dentro do próprio
método de negócio — as duas linhas acima vieram do nome de `place_order`, dos nomes de seus
parâmetros e do seu valor de retorno, a informação que o código já tinha, não de uma chamada que
alguém escreveu.

## Onde isso está conectado nos exemplos

Todo exemplo executável em `examples/` envia seu trace para um logger configurado de forma
realista, ao lado da sua narração de console — `logging.basicConfig` na raiz de composição mais
`LoggingTraceConsumer`/`NarrativeContextFilter` desta guia, não um trecho copiado num README. Veja
[`examples/README.md`](../../examples/README.md#where-the-logger-is-configured) para saber qual
arquivo configura qual exemplo.
