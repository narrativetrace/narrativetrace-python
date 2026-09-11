<!-- source: documentation/guides/configuration.md blob f45d36689e76 | translated: 2026-09-11 | reviewed: - -->

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
| `output` | `NARRATIVETRACE_OUTPUT` | truthy → grava artefatos por teste | ligado |
| `output_dir` | `NARRATIVETRACE_OUTPUT_DIR` | diretório de artefatos | `narrative-traces` |
| `format` | `NARRATIVETRACE_FORMAT` | `markdown` / `text` / `mermaid` / `plantuml` | `markdown` |
| `level` | `NARRATIVETRACE_LEVEL` | nível de captura para o contexto da fixture | `DETAIL` |
| `glossary_dir` | `NARRATIVETRACE_GLOSSARY_DIR` | diretório com o `glossary.json` commitado, lido como o vocabulário para a pontuação de clareza (ver [guia-de-clareza.md](guia-de-clareza.md)) | diretório de trabalho |
| `canonical` | `NARRATIVETRACE_CANONICAL` | também grava o array de entradas `<test>.canonical.json` por teste | `false` |

`output` vem ligado por padrão: a fixture `narrative_trace` grava os artefatos de cada teste não
vazio sob `narrative-traces/` sem nenhuma configuração. Desative com `NARRATIVETRACE_OUTPUT=false`
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

## Identidade do serviço

Estampe metadados do serviço em cada span para correlação:

```python
from narrativetrace import ServiceIdentity

context = ContextVarNarrativeContext(service_identity=ServiceIdentity("orders", "1.4.0", "prod"))
```
