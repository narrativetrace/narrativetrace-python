<!-- source: documentation/guides/pytest.md blob 58aa4f70d42a | translated: 2026-09-12 | reviewed: - -->

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
- **Artefatos** — ativados por padrão *(since 0.1.2, unreleased)*: cada teste não vazio grava um
  arquivo de trace — e, para markdown, um documento de cenário `.json`, `diagrams/<Class>/<slug>.mmd`,
  e um artefato `structural/<Class>/<slug>.nt` livre de valores *(since 0.1.2, unreleased)* — sob
  `NARRATIVETRACE_OUTPUT_DIR` (padrão `narrative-traces`; coloque no seu `.gitignore`, veja
  [o-que-commitar.md](o-que-commitar.md)). O resultado do cenário é `PASSED` ou `FAILED`. Desative
  com `NARRATIVETRACE_OUTPUT=false` (ou `output = false` em um arquivo de configuração, veja
  [guia-de-configuracao.md](guia-de-configuracao.md)). A versão publicada no PyPI,
  `narrativetrace-pytest==0.1.1`, ainda vem desativada; nela, ative
  `NARRATIVETRACE_OUTPUT=true` explicitamente.
- **Delta estrutural + modo de aprovação** *(since 0.1.2, unreleased)* — o arquivo `.nt` em disco é
  a última baseline verde; o rodapé da suíte imprime um resumo `Since last green: …`, e o relatório
  de um teste que falha imprime seu delta estrutural em vez do trace completo quando a forma mudou.
  Ligue `NARRATIVETRACE_APPROVAL=true` para em vez disso falhar um teste contra um trace
  `.approved.nt` commitado — veja o [Formato de trace estrutural](formato-de-trace-estrutural.md) e
  o [Guia de configuração](guia-de-configuracao.md).
- **Rodapé de clareza** — o rodapé da suíte imprime uma divisão `Clarity: X% high | Y% moderate |
  Z% low`, e (quando a saída está habilitada) grava `clarity-results.json` + `clarity-report.md` com
  uma entrada por teste traçado.

> Um id de `@pytest.mark.parametrize` (`test_finds_it[KAYAK]`) chega ao *nome de arquivo* do
> artefato que carrega valores e ao seu cabeçalho `scenario:`/`**Scenario:**`, e ao
> `manifest.json`, exatamente como antes — nunca é cortado ou ocultado. O artefato estrutural `.nt`
> livre de valores é o único lugar onde isso *é* resolvido para você: o cabeçalho estrutural de uma
> invocação é intitulado pelo método e seu índice de invocação, nunca pelo id de parametrize
> *(since 0.1.2, unreleased)* — veja o
> [Formato de trace estrutural](formato-de-trace-estrutural.md). Mantenha segredos fora dos ids de
> `parametrize` de qualquer forma; veja
> [Privacidade e ocultação § Não garantias](privacidade-e-ocultacao.md#não-garantias).

## Níveis nos testes

`NARRATIVETRACE_LEVEL=OFF` não captura nada (árvore vazia); um valor desconhecido degrada para
`DETAIL` sem erro. O nível pode igualmente vir de um arquivo de configuração — o ambiente
simplesmente vence sobre ele.
