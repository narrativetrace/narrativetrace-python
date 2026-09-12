<!-- source: documentation/sixty-seconds.md blob 70bd8901cadf | translated: 2026-09-12 | reviewed: - -->

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

```python
# main.py
from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, trace_object


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(IndentedTextRenderer().render(context.capture_trace()))
```

## 3. Rode

```bash
uv run main.py
```

```text
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
-from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, trace_object
+import logging
+import sys
+
+from narrativetrace import (
+    ContextVarNarrativeContext,
+    IndentedTextRenderer,
+    export_to_logger,
+    trace_object,
+)
 
 
 class OrderService:
     def place_order(self, customer_id, product_id, quantity):
         return f"ORD-{customer_id}-{product_id}-{quantity}"
 
 
+logging.basicConfig(level=logging.DEBUG, format="%(message)s", stream=sys.stdout)
+
 context = ContextVarNarrativeContext()
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
OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
→ OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
← returned: "ORD-cust-1-prod-42-3"
```

(o tempo varia — o `0ms` é o que a sua máquina mediu, igual acima). O mesmo trace agora chega ao
destino de logs que você já tinha; a linha do console permanece intacta. Quem usa `structlog` recebe
o mesmo conjunto de chaves via `narrativetrace-structlog` — veja o [Guia de logging](guia-de-logging.md)
completo para `NarrativeContextFilter`, as chaves MDC e a correlação em nível de request.

## A seguir

| Você quer | Vá para |
|---|---|
| Traces da sua suíte de testes em vez de um script | [Guia de pytest](guia-de-pytest.md) |
| Manter um valor fora do trace | [Privacidade e ocultação](privacidade-e-ocultacao.md) |
| Uma pontuação de clareza de nomes para este código | [Guia de clareza](guia-de-clareza.md) |
| Níveis de tracing, configurações de saída, precedência | [Guia de configuração](guia-de-configuracao.md) |
| Algo acima não funcionou como mostrado | [Solução de problemas](solucao-de-problemas.md) |
