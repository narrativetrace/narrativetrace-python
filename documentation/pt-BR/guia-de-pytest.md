<!-- source: documentation/guides/pytest.md blob a44c1857df02 | translated: 2026-09-12 | reviewed: - -->

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
  arquivo de trace — e, para markdown, um documento de cenário `.json` mais
  `diagrams/<Class>/<slug>.mmd` — sob `NARRATIVETRACE_OUTPUT_DIR` (padrão `narrative-traces`;
  coloque no seu `.gitignore`, veja [o-que-commitar.md](o-que-commitar.md)). O resultado do cenário
  é `PASSED` ou `FAILED`. Desative com `NARRATIVETRACE_OUTPUT=false` (ou `output = false` em um
  arquivo de configuração, veja [guia-de-configuracao.md](guia-de-configuracao.md)). A versão
  publicada no PyPI, `narrativetrace-pytest==0.1.1`, ainda vem desativada; nela, ative
  `NARRATIVETRACE_OUTPUT=true` explicitamente.
- **Rodapé de clareza** — o rodapé da suíte imprime uma divisão `Clarity: X% high | Y% moderate |
  Z% low`, e (quando a saída está habilitada) grava `clarity-results.json` + `clarity-report.md` com
  uma entrada por teste traçado.

> Um id de `@pytest.mark.parametrize` (`test_finds_it[KAYAK]`) chega tanto ao *nome de arquivo* do
> artefato quanto ao cabeçalho `scenario:`/`**Scenario:**` — nunca é cortado ou ocultado. O único
> artefato que este plugin grava é do tipo que carrega valores (veja o
> [Guia de funcionalidades](guia-de-funcionalidades.md): um artefato estrutural livre de
> valores, que o contrato multiplataforma de nomeação intitularia sem o id de `parametrize`,
> ainda não tem equivalente em Python). Mantenha segredos fora dos ids de `parametrize`; veja
> [Privacidade e ocultação § Não garantias](privacidade-e-ocultacao.md#não-garantias).

## Níveis nos testes

`NARRATIVETRACE_LEVEL=OFF` não captura nada (árvore vazia); um valor desconhecido degrada para
`DETAIL` sem erro. O nível pode igualmente vir de um arquivo de configuração — o ambiente
simplesmente vence sobre ele.
