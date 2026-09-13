<!-- source: documentation/sixty-seconds.md blob c9e26b0afb36 | translated: 2026-09-13 | reviewed: - -->

# Veja um trace em 60 segundos

Sem linhas `logger.info(...)`, sem framework de testes, nada para abrir depois — um script simples,
uma execução, e o trace aparece direto no seu terminal. Tudo abaixo foi executado de verdade contra o
pacote publicado no PyPI (`narrativetrace` 0.1.1) — a saída está colada, não imaginada.

## 1. Projeto novo, instale o pacote

```bash
uv init myproject && cd myproject
uv add narrativetrace
```

## 2. O programa

`main.py` adota um id de trace fixo — o mesmo mecanismo que uma fronteira ao estilo servlet usa
para um cabeçalho de trace de entrada — apenas para que a saída desta página sempre nomeie o mesmo
trace. O seu próprio código nunca faz isso: uma execução real gera um id de trace aleatório a cada
vez, e o nome de três palavras abaixo é derivado dele, nunca de um nome que você escolhe.

```python
# main.py
from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, TraceId, trace_object


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


# Um id de trace fixo, adotado para que a saída incorporada desta página sempre nomeie o mesmo
# trace. Uma execução real gera um aleatório a cada vez (nunca este — é a constante própria desta
# DEMO, não o padrão da biblioteca) pelo mesmo TraceId.adopt_trace_id que uma fronteira ao estilo
# servlet usa para um cabeçalho de trace de entrada.
DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(IndentedTextRenderer().render(context.capture_trace()))
```

## 3. Rode

```bash
uv run main.py
```

```text
trace: loose hook parks (a1b2c3d)

OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
```

`0ms` também é real — essa chamada rodou em menos de um milissegundo. Uma máquina mais lenta ou um
método mais pesado mostram um número maior; o ponto é que ele é sempre medido, nunca fabricado.

Você não escreveu uma única declaração de log. Essa linha veio do nome do método (`place_order`), dos
nomes dos parâmetros (`customer_id`, `product_id`, `quantity`) e do valor de retorno real — a
informação que seu código já tinha.

## O que acabou de acontecer

- **`ContextVarNarrativeContext()`** é o contexto de captura — onde os eventos de
  entrada/retorno/exceção caem enquanto seu código roda. Ele se propaga por `contextvars`, então segue
  tasks assíncronas e trabalho de thread-pool sem que você precise repassá-lo manualmente.
- **`trace_object(OrderService(), context)`** envolve uma instância real. Toda chamada a um método
  público do wrapper é capturada; o objeto por baixo fica intacto — sem classe base, sem decorador no
  próprio `place_order`, sem registro.
- **`context.capture_trace()` mais um renderizador** transforma os eventos capturados em texto.
  `IndentedTextRenderer` é o que você acabou de ver; `MarkdownRenderer` renderiza a mesma chamada como
  um item Markdown — a forma que `narrativetrace-pytest` grava em disco por padrão — e `ProseRenderer`
  se lê como uma frase. Mesmo trace, três formas.

## Envie para o seu logger

A linha no console é boa para um script; em produção você quer o trace no fluxo de logs que você
já tem. `export_to_logger` envia um trace já capturado para o seu logger em uma única chamada
*(since 0.1.2, unreleased)* — a ponte para o `logging` da biblioteca padrão que o NarrativeTrace
já traz; na própria `0.1.1` publicada, reproduza `store.events()` através do
`LoggingTraceConsumer` manualmente):

```diff
 # main.py
--from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, trace_object
+-from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, TraceId, trace_object
+import logging
+import sys
+
+from narrativetrace import (
+    ContextVarNarrativeContext,
+    IndentedTextRenderer,
+    NarrativeContextFilter,
+    TraceId,
+    export_to_logger,
+    trace_object,
+)
 
 
 class OrderService:
     def place_order(self, customer_id, product_id, quantity):
         return f"ORD-{customer_id}-{product_id}-{quantity}"
 
 
+ # Um id de trace fixo, adotado para que a saída incorporada desta página sempre nomeie o mesmo
+ # trace. Uma execução real gera um aleatório a cada vez (nunca este — é a constante própria desta
+ # DEMO, não o padrão da biblioteca) pelo mesmo TraceId.adopt_trace_id que uma fronteira ao estilo
+ # servlet usa para um cabeçalho de trace de entrada.
+ DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")
+
+handler = logging.StreamHandler(sys.stdout)
+handler.addFilter(NarrativeContextFilter())
+logging.basicConfig(
+    level=logging.DEBUG, format="[%(traceName)s] [%(runName)s] %(message)s", handlers=[handler]
+)
+
 context = ContextVarNarrativeContext()
+context.adopt_trace_id(DEMO_TRACE_ID)
 service = trace_object(OrderService(), context)
 service.place_order("cust-1", "prod-42", 3)
 
-print(IndentedTextRenderer().render(context.capture_trace()))
+trace = context.capture_trace()
+print(IndentedTextRenderer().render(trace))
+
+export_to_logger(trace)
```

```bash
uv run main.py
```

```text
trace: loose hook parks (a1b2c3d)

OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
[loose hook parks] [] → OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
[loose hook parks] [] ← returned: "ORD-cust-1-prod-42-3"
```

(o tempo varia — o `0ms` é o que a sua máquina mediu, igual acima; a frase entre colchetes é sempre
a mesma — a repetição do `export_to_logger` carrega o próprio id do trace capturado, então
`traceName` aqui nomeia o mesmo trace fixado acima, nunca um novo). `traceName` vem preenchido
porque há um trace ativo; `runName` está vazio aqui porque esse
script simples não pertence a nenhuma execução de suíte de testes — ele só é preenchido sob o
fixture do `narrativetrace-pytest` (veja [Guia de configuração, § A execução tem um
nome](guia-de-configuracao.md#a-execução-tem-um-nome)). O mesmo trace agora chega ao destino de
logs que você já tinha; a linha do console permanece intacta. Quem usa `structlog` recebe o mesmo
conjunto de chaves via `narrativetrace-structlog` — veja o [Guia de logging](guia-de-logging.md)
completo para `NarrativeContextFilter`, as chaves MDC e a correlação em nível de request.

## A seguir

| Você quer | Vá para |
|---|---|
| Traces da sua suíte de testes em vez de um script | [Guia de pytest](guia-de-pytest.md) |
| Manter um valor fora do trace | [Privacidade e ocultação](privacidade-e-ocultacao.md) |
| Uma pontuação de clareza de nomes para este código | [Guia de clareza](guia-de-clareza.md) |
| Níveis de tracing, configurações de saída, precedência | [Guia de configuração](guia-de-configuracao.md) |
| Algo acima não funcionou como mostrado | [Solução de problemas](solucao-de-problemas.md) |
