<!-- source: documentation/guides/configuration.md blob bfd3d507ba8f | translated: 2026-09-18 | reviewed: - -->

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

## Dois botões, dois caminhos

**Configurei o nível de tracing para `DETAIL`, mas nada aparece nos meus logs. Ou: configurei meu
logger para `WARNING` e a trace ainda aparece nos meus artefatos do pytest. Qual ajuste vence?**

Os dois, porque respondem perguntas diferentes. O NarrativeTrace tem dois botões, e levar uma
trace capturada até o seu logger é um passo separado de capturá-la.

**Botão 1, o nível de tracing, decide o que é capturado.** `OFF`, `ERRORS`, `SUMMARY`,
`NARRATIVE`, `DETAIL` — cumulativos, cada um incluindo tudo o que está abaixo (a tabela acima). É
o próprio ajuste do NarrativeTrace, e atua em dois pontos diferentes, não em um só: em `OFF`,
`context.is_active()` é `False` e o wrapper do `trace_object` pula a interceptação por completo —
a chamada envolvida roda sem tocar em nada do maquinário de captura, e nada vira um evento, para
nenhum consumidor. A partir de `ERRORS`, toda chamada *é* interceptada e registrada — `ERRORS` e
`SUMMARY` não pulam a interceptação, eles podam a árvore resultante *depois* da captura
(descartando caminhos sem erro, colapsando frames intermediários); só abaixo de `DETAIL` os
valores de parâmetros ficam de fora no momento da captura, irrecuperáveis depois, não importa o
que o logger faça. Nenhum outro ajuste consegue trazer de volta o que `OFF` pulou ou o que só
`DETAIL` captura.

**Botão 2, o nível do seu logger, decide o que é impresso — uma vez que uma trace chega ao seu
logger.** Por padrão, nenhuma chega: o NarrativeTrace não escreve nada em `logging.getLogger
("narrativetrace")` (o nome de logger que `LoggingTraceConsumer` usa) a menos que você mesmo
envie uma trace para lá. Quando você faz isso, cada tipo de linha tem seu próprio nível padrão:
uma entrada e um retorno em `DEBUG` (a biblioteca padrão `logging` do Python não tem um nível
`TRACE` para espelhar o do Java), uma exceção em `WARNING` como `!! {type}: {message}
[{error_context}]`. O limiar do seu logger então faz o que sempre faz — subi-lo silencia linhas.
Ele nunca captura mais, e nunca captura menos.

**Agora os dois caminhos, que é de onde vem a confusão.** A trace capturada — tudo o que
`capture_trace()` retorna, e tudo que depende dela: os artefatos por teste do plugin de pytest, a
linha de base de aprovação `.nt`, o relatório de clareza, a exportação em lote do OpenTelemetry
feita por `TraceSpanExporter`, a narrativa renderizada — é escrita diretamente no armazenamento de
eventos do próprio contexto no momento em que cada método entra e sai. Essa escrita nunca consulta
o seu logger, em nenhuma direção: um logger `narrativetrace` em `CRITICAL` não a reduz, e a
ausência total de logger também não.

Enviar uma trace capturada para o seu logger é um passo separado e explícito, através de
`LoggingTraceConsumer`, e há duas formas de fazer isso:

- **Reprodução após a captura** — `export_to_logger(trace)` envia uma `TraceTree` já finalizada
  através de um `LoggingTraceConsumer` privado em uma única chamada. Esse é o caminho que o
  [tutorial de 60 segundos](sessenta-segundos.md#envie-para-o-seu-logger) e todo guia deste
  repositório usam.
- **Ao vivo, à medida que os eventos acontecem** — anexe um `LoggingTraceConsumer` como o listener
  síncrono de um `DualPathPipeline` que você monta por conta própria, normalmente junto com um
  `BufferedEventConsumer` como seu caminho de melhor esforço (um anel limitado, 65.536 eventos por
  padrão, com descarte de carga sob pressão, cada perda contabilizada — veja
  [Concorrência](../../README.md#concurrency)) para qualquer outro consumidor ao vivo, incluindo um
  `OtelTraceEventListener`, alimentado pelo mesmo fluxo de eventos.

De qualquer forma, a linha de log e o artefato de trace são dois leitores independentes dos mesmos
eventos capturados. Subir o nível do logger `narrativetrace` silencia linhas de log; isso não pode
alcançar a saída de `capture_trace()`, porque essa saída nunca passou pelo logger.

**Onde cada botão mora.**

| Botão | Onde mora |
|---|---|
| Nível de tracing | Variável de ambiente `NARRATIVETRACE_LEVEL`; `level` em `narrativetrace.toml` ou `[tool.narrativetrace]` em `pyproject.toml`; `NarrativeTraceConfig(level=TracingLevel.X)` no código |
| Limiar do logger | Configuração comum do `logging` em `logging.getLogger("narrativetrace")` — o nome que `LoggingTraceConsumer` usa por padrão |
| Nível por tipo de linha | `LoggingTraceConsumer(levels={EventType.ENTRY: ..., EventType.RETURN: ..., EventType.EXCEPTION: ...})`, ou o mesmo argumento `levels=` passado através de `export_to_logger(trace, levels=...)` |

**Regras práticas.** Para reduzir o volume de logs, suba o limiar do logger `narrativetrace`; a
trace capturada permanece intocada. Para reduzir o tamanho da trace, baixe o nível de tracing —
`ERRORS`/`SUMMARY` a podam depois da captura. Para reduzir o overhead, baixe o nível de tracing
até `OFF`: esse é o único passo que pula a interceptação em si; `ERRORS`, `SUMMARY` e `NARRATIVE`
continuam interceptando e registrando cada chamada do mesmo jeito que `DETAIL`, só que renderizam
menos valores e podam mais depois. O limiar do logger não muda nada no custo de captura, em
nenhum nível. Para manter o tracing ativo em produção mas fora dos logs, deixe o nível de tracing
em `SUMMARY` ou acima e, ou não envie traces para o seu logger, ou envie e defina o logger
`narrativetrace` para `WARNING`: de qualquer forma, `capture_trace()` e tudo que depende dela
permanecem completos.

## Configurações de saída (plugin do pytest)

| Chave | Variável de ambiente | Significado | Padrão |
|---|---|---|---|
| `output` | `NARRATIVETRACE_OUTPUT` | truthy → grava artefatos por teste | ligado *(since 0.1.2)* |
| `output_dir` | `NARRATIVETRACE_OUTPUT_DIR` | diretório de artefatos | `narrative-traces` |
| `format` | `NARRATIVETRACE_FORMAT` | `markdown` / `text` / `mermaid` / `plantuml` | `markdown` |
| `level` | `NARRATIVETRACE_LEVEL` | nível de captura para o contexto da fixture | `DETAIL` |
| `glossary_dir` | `NARRATIVETRACE_GLOSSARY_DIR` | diretório com o `glossary.json` commitado, lido como o vocabulário para a pontuação de clareza (ver [guia-de-clareza.md](guia-de-clareza.md)) | diretório de trabalho |
| `canonical` | `NARRATIVETRACE_CANONICAL` | também grava o array de entradas `<test>.canonical.json` por teste | `false` |
| `approval` | `NARRATIVETRACE_APPROVAL` | truthy → verifica a estrutura contra um trace aprovado commitado *(since 0.1.2)* | `false` |
| `approved_dir` | `NARRATIVETRACE_APPROVED_DIR` | diretório com os traces `*.approved.nt` commitados *(since 0.1.2)* | `test-narratives` |

`output` vem ligado por padrão *(since 0.1.2)* — a versão publicada no PyPI, `0.1.1`,
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

## Artefato estrutural e modo de aprovação

*(since 0.1.2)*

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

Toda execução também grava `<output_dir>/manifest.json`: um objeto `run` de nível superior
(`id`, `name` — a frase de três palavras própria da execução, *(since 0.1.2)*, veja
[A execução tem um nome](#a-execução-tem-um-nome) abaixo) seguido de uma linha por cenário
traçado, nomeando seu teste, seu número de invocação quando o método rodou mais de uma vez, e cada
artefato que possui:

```json
{
  "schema": "narrativetrace/scenario-manifest/1",
  "run": {
    "id": "a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4",
    "name": "bold elk soars"
  },
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
  run: bold elk soars
  2 scenarios recorded
  Clarity: 100% high | 0% moderate | 0% low
  Reports: narrative-traces
  Since last green: 1 scenario unchanged · 1 changed: "Customer places order" (+1 call InventoryService.release)
```

O relatório de console de um teste que falha imprime o delta estrutural contra o artefato da
última execução verde em vez do trace completo, quando a estrutura realmente mudou.

### A execução tem um nome

*(since 0.1.2)* Um id de execução é gerado por cada sessão do pytest — o próprio hook
`pytest_sessionstart` do plugin — um id com forma W3C, nunca uma constante compartilhada — e sua
frase de três palavras (o mesmo gerador de nomes de onde vem o nome de um id de trace) é o **nome
da execução**. Ele aparece:

- no rodapé da suíte no console (`run: bold elk soars`, acima);
- no objeto `run` de nível superior do `manifest.json` (`id` e `name`, acima);
- no frontmatter YAML de todo documento Markdown de trace (`run: bold elk soars`, ao lado de
  `scenario:`);
- no contexto análogo ao MDC da ponte de logging da biblioteca padrão como `runName` para toda a
  sessão (veja o [Guia de logging](guia-de-logging.md)), de modo que um único grep encontra as
  linhas de log de uma execução.

O nome da execução e o seu id são protegidos pelo mesmo invariante que o próprio nome de um trace:
**nunca** chegam ao texto estrutural `.nt`, a um trace aprovado ou received, ao nome de um
artefato, nem às chaves por cenário do manifesto — rodar a mesma suíte duas vezes, com dois nomes
de execução diferentes, produz arquivos `.nt` idênticos byte a byte e a mesma saída de delta todas
as vezes. O próprio nome de um trace (`trace: bold elk soars (a1b2c3d)` no renderer de console/
indentado, `The trace bold elk soars:` em prosa, a frase na linha de título do Markdown) é algo
*diferente* — um por trace, não um por execução — e está igualmente ausente do texto `.nt`.

## Identidade do serviço

Estampe metadados do serviço em cada span para correlação:

```python
from narrativetrace import ServiceIdentity

context = ContextVarNarrativeContext(service_identity=ServiceIdentity("orders", "1.4.0", "prod"))
```
