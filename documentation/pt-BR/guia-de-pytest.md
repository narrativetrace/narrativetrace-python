<!-- source: documentation/guides/pytest.md blob 633109ebae77 | translated: 2026-09-03 | reviewed: 2026-09-03 -->

# Plugin do pytest

`narrativetrace-pytest` se registra automaticamente (entry point). Solicite a fixture
`narrative_trace` para obter um contexto de captura novo por teste.

```python
from narrativetrace import trace_object

def test_place_order(narrative_trace):
    service = trace_object(OrderService(narrative_trace), narrative_trace)
    service.place_order("cust-1", "prod-42", 3)
```

## O que você ganha

- **Narrativas de falha** — um teste que falha imprime um bloco emoldurado `Scenario: …` com o trace
  de execução indentado, então o caminho da chamada *é* o diagnóstico.
- **Avisos de template** — tokens `@narrated`/`@on_error` não resolvidos são reportados uma vez por
  execução.
- **Artefatos** — com `NARRATIVETRACE_OUTPUT=1` (ou `output = true` em um arquivo de configuração,
  veja [guia-de-configuracao.md](guia-de-configuracao.md)), cada teste não vazio grava um arquivo de
  trace — e, para markdown, um documento de cenário `.json` mais `diagrams/<Class>/<slug>.mmd` — sob
  `NARRATIVETRACE_OUTPUT_DIR`. O resultado do cenário é `PASSED` ou `FAILED`.
- **Rodapé de clareza** — o rodapé da suíte imprime uma divisão `Clarity: X% high | Y% moderate |
  Z% low`, e (quando a saída está habilitada) grava `clarity-results.json` + `clarity-report.md` com
  uma entrada por teste traçado.

## Níveis nos testes

`NARRATIVETRACE_LEVEL=OFF` não captura nada (árvore vazia); um valor desconhecido degrada para
`DETAIL` sem erro. O nível pode igualmente vir de um arquivo de configuração — o ambiente
simplesmente vence sobre ele.
