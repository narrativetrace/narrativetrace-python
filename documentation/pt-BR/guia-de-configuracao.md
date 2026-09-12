<!-- source: documentation/guides/configuration.md blob c618d3b8ea67 | translated: 2026-09-12 | reviewed: - -->

# Configuração

## De onde vêm as configurações

Toda configuração é resolvida por uma única cadeia. A primeira fonte que tiver
a chave vence:

1. **Ambiente** — `NARRATIVETRACE_<KEY>` (a chave em maiúsculas, então
   `output_dir` lê `NARRATIVETRACE_OUTPUT_DIR`)
2. **`narrativetrace.toml`** — chaves na raiz do documento
3. **`pyproject.toml`** — chaves sob `[tool.narrativetrace]`
4. **Valor padrão embutido**

Os arquivos de configuração são encontrados subindo a partir do diretório de
trabalho. O diretório mais próximo que tiver qualquer um dos dois arquivos
vence, e a busca para ali.

**Duas fontes de configuração no mesmo diretório é um erro fatal.** Se um
diretório tiver tanto um `narrativetrace.toml` quanto um `pyproject.toml` com
uma tabela `[tool.narrativetrace]`, a resolução lança
`DuplicateConfigurationError` em vez de escolher uma silenciosamente. Um
arquivo malformado ainda conta como uma fonte declarada — uma configuração
quebrada deve falhar de forma ruidosa, não perder no cara ou coroa.

```toml
# narrativetrace.toml
level = "NARRATIVE"
output = true
output_dir = "narrative-traces"
format = "markdown"
```

```toml
# ...ou em pyproject.toml — nunca os dois no mesmo diretório
[tool.narrativetrace]
level = "NARRATIVE"
output = true
```

```bash
# O ambiente sempre vence, para sobrescritas pontuais
export NARRATIVETRACE_LEVEL=OFF
```

## Nível de tracing

A captura é controlada por um nível de tracing, verificado *antes* de
qualquer renderização acontecer. Os níveis são cumulativos — cada um inclui
tudo o que está abaixo dele.

| Nível | Captura |
|---|---|
| `OFF` | nada (os wrappers fazem short-circuit; o caminho mais barato possível) |
| `ERRORS` | apenas os caminhos que terminaram em erro ou nunca completaram |
| `SUMMARY` | pontos de entrada mais suas chamadas folha e de erro, frames intermediários colapsados |
| `NARRATIVE` | a estrutura completa de chamadas com a prosa resolvida de `@narrated` |
| `DETAIL` | + valores de parâmetros e retorno (padrão) |

Os valores de parâmetros são descartados **no momento da captura** abaixo de
`DETAIL`, então não podem ser recuperados depois a partir de um trace de
nível mais baixo. `ERRORS` e `SUMMARY` também podam a árvore após a captura.

Defina no código, em um arquivo de configuração, ou pelo ambiente:

```python
from narrativetrace import ContextVarNarrativeContext, NarrativeTraceConfig, TracingLevel

context = ContextVarNarrativeContext(NarrativeTraceConfig(level=TracingLevel.NARRATIVE))
```

`NarrativeTraceConfig.resolve()` roda a cadeia acima para a chave `level`.
Valores desconhecidos ou vazios degradam para o padrão em vez de lançar
exceção — uma configuração incorreta nunca deve derrubar a captura junto.
Os nomes de nível não diferenciam maiúsculas de minúsculas.

## Configurações de saída (plugin do pytest)

| Chave | Variável de ambiente | Significado | Padrão |
|---|---|---|---|
| `output` | `NARRATIVETRACE_OUTPUT` | truthy → grava artefatos por teste | ligado *(since 0.1.2, unreleased)* |
| `output_dir` | `NARRATIVETRACE_OUTPUT_DIR` | diretório de artefatos | `narrative-traces` |
| `format` | `NARRATIVETRACE_FORMAT` | `markdown` / `text` / `mermaid` / `plantuml` | `markdown` |
| `level` | `NARRATIVETRACE_LEVEL` | nível de captura para o contexto da fixture | `DETAIL` |
| `glossary_dir` | `NARRATIVETRACE_GLOSSARY_DIR` | diretório com o `glossary.json` commitado, lido como o vocabulário para a pontuação de clareza (ver [guia-de-clareza.md](guia-de-clareza.md)) | diretório de trabalho |
| `canonical` | `NARRATIVETRACE_CANONICAL` | também grava o array de entradas `<test>.canonical.json` por teste | `false` |
| `approval` | `NARRATIVETRACE_APPROVAL` | truthy → verifica a estrutura contra um trace aprovado commitado *(since 0.1.2, unreleased)* | `false` |
| `approved_dir` | `NARRATIVETRACE_APPROVED_DIR` | diretório com os traces `*.approved.nt` commitados *(since 0.1.2, unreleased)* | `test-narratives` |

`output` vem ligado por padrão *(since 0.1.2, unreleased)* — a versão publicada no PyPI, `0.1.1`,
ainda vem desligada: a fixture `narrative_trace` grava os artefatos de cada teste não vazio sob
`narrative-traces/` sem nenhuma configuração. Desative com `NARRATIVETRACE_OUTPUT=false`
(`0`/`no`/`off` também funcionam, sem diferenciar maiúsculas de minúsculas) ou `output = false` em
um arquivo de configuração — veja [o-que-commitar.md](o-que-commitar.md) para colocar o diretório
no seu `.gitignore`.

`glossary_dir` é lido exista ou não um glossário: ler não muda nada em
disco, então não precisa de opt-in, e um repositório sem o arquivo pontua
apenas com os dicionários embutidos.

Os nomes de formato são comparados sem diferenciar maiúsculas de minúsculas.
Somente `markdown` grava os companheiros acoplados (um `.json` canônico
irmão e um `.mmd` Mermaid); `text`, `mermaid` e `plantuml` substituem o
trace em Markdown por esse único artefato.

`canonical` é independente de `format`: uma execução que escolheu `text` ou
`mermaid` para seu artefato legível por humanos ainda deve suas entradas a
um executor de conformidade. O arquivo é um array JSON plano de entradas
canônicas no esquema `1.2`, um `method_enter` e um `method_exit` por chamada
traçada, cada uma válida contra `entry.schema.json`. Vem desligado por
padrão porque é um artefato para máquinas — para outras implementações, fixtures de
conformidade e tradução — não algo para ler depois de uma falha.

## Artefato estrutural e modo de aprovação *(since 0.1.2, unreleased)*

O caminho Markdown também grava um artefato estrutural `.nt` livre de valores ao lado da
narrativa — veja o [Formato de trace estrutural](formato-de-trace-estrutural.md) para a gramática.
O arquivo em disco é a **última baseline verde**: uma execução verde a avança, uma execução que
não está verde é comparada contra ela mas nunca a sobrescreve, então cada delta se lê como "o que
mudou desde a última vez que este cenário passou". "Verde" é o veredito completo, não apenas as
asserções — um teste que passou mas cuja estrutura foi *rejeitada* pelo modo de aprovação termina
não verde, e sua estrutura não é gravada. Rejeitar uma mudança, portanto, deixa a baseline onde
estava, e reverter a mudança não relata nenhum delta.

`approval` liga o modo de aprovação: depois de um teste **que passa**, a estrutura livre de
valores do cenário é verificada contra a baseline commitada
`<approved_dir>/<TestClassName>/<slug>.approved.nt`. Uma baseline ausente ou uma diferença
estrutural falha o teste com um diff legível e grava a estrutura atual ao lado da baseline como
`*.received.nt`. Revise-o, depois promova com `uv run poe approve` (ou o script de console
`narrativetrace-approve`, que lê essa mesma chave `approved_dir`). Testes que falham nunca são
verificados — a aprovação só julga um teste que de outra forma teria passado.

Toda execução também grava `<output_dir>/manifest.json`: uma linha por cenário traçado, nomeando
seu teste, seu número de invocação quando o método rodou mais de uma vez, e cada artefato que
possui:

```json
{
  "schema": "narrativetrace/scenario-manifest/1",
  "scenarios": [
    {
      "scenario": "find TENT",
      "testClass": "CatalogTest",
      "testMethod": "test_finds_it",
      "invocation": 2,
      "artifacts": {
        "trace": "traces/CatalogTest/test_finds_it-002-tent.md",
        "structural": "structural/CatalogTest/test_finds_it-002-tent.nt"
      }
    }
  ]
}
```

O rodapé da suíte imprime mais uma linha resumindo o status estrutural de cada cenário:

```
NarrativeTrace — Suite complete
  2 scenarios recorded
  Clarity: 100% high | 0% moderate | 0% low
  Reports: narrative-traces
  Since last green: 1 scenario unchanged · 1 changed: "Customer places order" (+1 call InventoryService.release)
```

O relatório de console de um teste que falha imprime o delta estrutural contra o artefato da
última execução verde em vez do trace completo, quando a estrutura realmente mudou.

## Identidade do serviço

Estampe metadados do serviço em cada span para correlação:

```python
from narrativetrace import ServiceIdentity

context = ContextVarNarrativeContext(service_identity=ServiceIdentity("orders", "1.4.0", "prod"))
```
