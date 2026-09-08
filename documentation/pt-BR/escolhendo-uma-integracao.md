<!-- source: documentation/choosing-an-integration.md blob 753ad8c19299 | translated: 2026-09-03 | reviewed: 2026-09-03 -->

# Escolhendo uma integração

O NarrativeTrace tem um único modelo de captura — um evento de entrada/saída publicado através do pipeline —
alcançado por um pequeno número de mecanismos de anexação. Esta página responde "de qual pacote eu realmente
preciso", primeiro como tabela de consulta, depois como diagrama de decisão, e por fim com as ressalvas de
cada caminho.

## Você quer... / Comece com...

| Você quer | Comece com |
|---|---|
| Traces em testes, com o mínimo de cabeamento | `narrativetrace-pytest` (fixture `narrative_trace`) |
| Controle explícito sobre o que é envolvido, em Python puro | `trace_object(obj, context)` — o core, sem necessidade de framework |
| Ciclo de vida de requisições do FastAPI/Starlette | `narrativetrace-asgi` |
| Propagar um trace para uma chamada HTTP downstream | `attach_traceparent` do `narrativetrace-asgi` (httpx) |
| Traces no seu fluxo de log de produção | `LoggingTraceConsumer` / `NarrativeContextFilter` (core) |
| Pipelines de structlog | `narrativetrace-structlog` |
| Spans do OpenTelemetry | `narrativetrace-otel` |
| Diagramas de sequência a partir de uma árvore capturada | `narrativetrace-diagrams` |
| Gate de CI para qualidade de nomes | script de console `narrativetrace-clarity` |
| Flask (WSGI) ou Django | Ainda não disponível — veja *Limites da plataforma* abaixo |

Esta é a mesma matriz que o [LEIAME.md raiz](../../LEIAME.md) carrega; ela também vive
aqui como âncora para o diagrama e os detalhes abaixo.

## A decisão

Existe exatamente um primitivo de captura — `trace_object(obj, context)` — e ele envolve qualquer objeto
Python concreto diretamente, reflexivamente, na instância que você passa a ele. Não há requisito de
interface ou classe base como uma integração baseada em proxy dinâmico precisaria, então a decisão é
realmente sobre *onde* o envolvimento acontece, não *se* um objeto se qualifica:

```text
Onde você quer que os traces comecem?
   |
   +-- Dentro da minha suíte de testes ------> narrativetrace-pytest
   |                                            (fixture narrative_trace; sem envolvimento manual)
   |
   +-- Ao redor de objetos específicos, script simples
   |   ou código de aplicação -----------------> trace_object(obj, context) diretamente (core)
   |
   +-- Através do ciclo de vida de uma requisição HTTP
   |     |
   |     +-- FastAPI / Starlette (ASGI) -------> narrativetrace-asgi
   |     +-- Flask / Django -------------------> ainda não disponível (veja Limites da plataforma)
   |
   +-- Junto com código que já roda
       entre threads ou tasks asyncio ---------> trace_object como acima, mais um
                                                  snapshot de contexto no limite
                                                  (veja Trabalho entre threads abaixo)
```

Não existe mecanismo de anexação em nível de bytecode e sem código (nenhum import hook, nenhuma
auto-instrumentação via `sitecustomize.py` incluída aqui) — todo caminho acima é uma chamada explícita
que seu código faz ou um middleware que você registra, nunca algo que reescreve suas classes ao carregá-las.

## Uma coisa que todo caminho compartilha

Todos os mecanismos acima constroem a mesma `TraceTree` a partir do mesmo stream de `TraceEvent` —
o `_TracedProxy` do `trace_object`, a fixture do pytest e o middleware ASGI todos acabam chamando
o mesmo contexto (`ContextVarNarrativeContext.capture_trace()`); nenhum deles define sua própria
noção de chamada capturada. Escolher uma integração é uma questão de *como a chamada é envolvida*,
nunca do que é registrado uma vez que ela é — todo caminho passa pelo mesmo ponto de captura por
design, uma decisão interna (PY-001, PY-004, PY-005) que esta página não precisa reabrir.

## Ressalvas por caminho

- **`trace_object`** — envolve a instância que você passa a ele; uma referência ao objeto *original*,
  não envolvido, ignora a captura completamente, então envolva no ponto em que seu código entrega o
  objeto (uma raiz de composição, uma factory, uma fixture), não depois. Todo método público (sem
  underscore inicial) é traçado automaticamente; não há lista de opt-in por método além dos decoradores.
- **`narrativetrace-pytest`** — se auto-registra como plugin do pytest; a fixture `narrative_trace`
  entrega um contexto por teste, então rastrear ao longo de múltiplos testes (um recurso com escopo de
  sessão) precisa do seu próprio contexto, construído à mão com `ContextVarNarrativeContext`.
- **ASGI (`narrativetrace-asgi`)** — apenas escopos HTTP são capturados (`scope["type"] == "http"`);
  escopos WebSocket e lifespan passam intocados. `excluded_paths` compara o caminho da requisição por
  string exata, não um glob ou prefixo — `/health` exclui somente `/health`, nunca `/health/live`.
- **Trabalho entre threads / entre tasks** — o `ContextVarNarrativeContext` isola threads *e* tasks
  asyncio por design (cada um tem sua própria visão). Trabalho submetido a um `ThreadPoolExecutor` ou
  lançado como uma `asyncio.Task` só se junta ao trace pai através de `ForkJoinGroup`/`FireAndForgetGroup`
  ou de um snapshot de contexto tomado no limite — uma thread ou task que nunca recebeu um permanece
  isolada, e sua chamada equivalente a `captureTrace()` vê apenas o próprio trabalho. Uma lacuna
  conhecida: fazer fork diretamente dentro de um método traçado `async def` resolve o pai através da
  pilha de chamadas síncrona, que está vazia ali, então filhos lançados dessa forma aparecem como
  novas raízes em vez de aninhados sob o chamador `async` — faça fork a partir de um método síncrono,
  ou de um thread pool, para manter o aninhamento.
- **`narrativetrace-otel`** — requer `opentelemetry-api>=1.20`; ele conecta uma `TraceTree` já
  capturada a spans do OTel (exportador em lote) ou escuta ao vivo — ele não substitui a própria
  configuração de SDK/exportador do OpenTelemetry.

## Limites da plataforma

Todo caminho acima assume CPython ≥ 3.12. O middleware do Flask (WSGI) e do Django está **planejado,
não lançado** — o mesmo contrato de limite de requisição do `narrativetrace-asgi` é a forma pretendida,
mas não há pacote para instalar hoje; veja o [Guia de funcionalidades](guia-de-funcionalidades.md) para
o status. Não há teste de compatibilidade com PyPy ou GraalPy.

## Receitas

Todo caminho na matriz tem um exemplo funcional em [`examples/`](../../examples) (veja
[`examples/README.md`](../../examples/README.md)) e um guia em [`guides/`](../guides) — esta página
responde *qual*, aqueles respondem *como*.
