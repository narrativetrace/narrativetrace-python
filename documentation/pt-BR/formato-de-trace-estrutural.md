<!-- source: documentation/structural-trace-format.md blob 7baee63cf348 | translated: 2026-09-12 | reviewed: - -->

# Formato de trace estrutural (`.nt`)

*(since 0.1.2, unreleased)*. O artefato de trace estrutural seguro para IA (ADR-002 do produto):
um arquivo por cenário de teste contendo apenas a *forma* do comportamento autorada pelo
desenvolvedor — zero valores de tempo de execução. Este formato é **multiplataforma**: toda
implementação do NarrativeTrace emite o formato idêntico, o que é o que permite que traces
aprovados e fixtures de conformidade viajem entre plataformas. Esta página espelha a própria
especificação do formato estrutural da implementação de referência — a gramática abaixo é
normativa e idêntica em toda linguagem em que este produto é distribuído.

## Arquivos e nomeação

| Arquivo | Papel |
|---|---|
| `<output_dir>/structural/<TestClass>/<slug>.nt` | Gravado ao lado do trace em Markdown; o arquivo em disco é a **última baseline verde** — uma execução que não está verde é comparada contra ele (delta no console, relatório de falha) mas nunca o sobrescreve. "Verde" é o veredito completo: um teste que passou mas cuja estrutura foi *rejeitada* pelo modo de aprovação termina não verde, então uma estrutura rejeitada nunca se torna a baseline e reverter a mudança não relata nenhum delta |
| `<approved_dir>/<TestClass>/<slug>.approved.nt` | Trace aprovado commitado (opt-in via `NARRATIVETRACE_APPROVAL=true`, diretório configurável via `NARRATIVETRACE_APPROVED_DIR`, padrão `test-narratives`) — um teste que passa cuja estrutura difere falha com um diff legível |
| `<slug>.received.nt` | Gravado ao lado do trace aprovado em uma divergência (ou quando ainda não existe um trace aprovado); revise-o, depois promova via `uv run poe approve` ou o script de console `narrativetrace-approve` |
| `<slug>.incomplete.nt` | O mesmo conteúdo, gravado no lugar de `.received.nt` quando a própria execução foi incompleta (o caminho de melhor esforço descartou eventos, ou recusou um scope async por ter atingido o limite de adoção). O verbo approve o ignora pelo nome: uma execução curta nunca deve se tornar a baseline commitada, ou toda execução completa posterior seria lida como tendo *adicionado* chamadas. Uma execução assim é comparada por contenção de subsequência em vez de igualdade — ausências são toleradas e nomeadas, qualquer coisa adicionada ou reordenada ainda falha |

A extensão do formato vai por último (`.approved.nt`, convenção do ApprovalTests) para que
editores e visualizadores de diff se guiem por `.nt`. Nota: `.nt` colide com RDF N-Triples em
alguns mapas de destaque de sintaxe; registre uma substituição em `.gitattributes` onde isso
importar.

### Identidade do artefato (multiplataforma)

`<slug>` acima é a **identidade do artefato** de uma invocação de teste, e toda implementação a
escreve da mesma forma — um artefato gravado por uma implementação é encontrado sob o mesmo nome
por outra:

- Um método de teste comum é seu nome convertido em slug: dividido por camel-case e por `_`, em
  minúsculas, com tudo fora de `[a-z0-9_]` substituído por `_` — `customerPlacesOrder` →
  `customer_places_order`.
- Uma invocação de um teste que roda mais de uma vez (qualquer caso de
  `@pytest.mark.parametrize`, ou uma fixture parametrizada) adiciona `-<index>-<label>`: o número
  de invocação em base 1 preenchido com zeros até três dígitos, seguido do rótulo legível da
  invocação passado pela mesma regra de slug com sequências de `_` colapsadas e as pontas
  aparadas — `equipment_can_be_found-002-find_tent`. Um rótulo que vira slug vazio é descartado,
  deixando `equipment_can_be_found-002`.
- `-` é o separador precisamente porque o alfabeto do slug não consegue produzi-lo. O índice — não
  o rótulo — é o que torna o esquema à prova de colisões: duas invocações sempre diferem nele,
  então rótulos que diferem apenas em caracteres que um caminho não consegue carregar ainda
  recebem arquivos separados. O rótulo é o que torna o nome legível.
- O nome é estável entre execuções, máquinas e processos, o que é o que permite que o
  `.approved.nt` de uma invocação seja commitado. Onde um nome excede o limite de 255 bytes por
  elemento de caminho, a metade do *método* é truncada e recebe oito caracteres hexadecimais do
  `String.hashCode` do Java sobre o slug completo — especificado, portanto idêntico em todo
  lugar; um hash por processo invalidaria silenciosamente toda baseline que tocasse.

Como os nomes de artefato são derivados em vez de anunciados, uma execução também grava
`<output_dir>/manifest.json`: uma linha por cenário traçado, nomeando seu teste, seu número de
invocação e cada arquivo que possui. Consulte-o quando souber o cenário e quiser o arquivo.

> O cabeçalho `scenario:` de uma invocação **não** é seu nome de exibição. Um id de `parametrize`
> interpola argumentos no nome de exibição do teste, então este artefato — o livre de valores — é
> intitulado pelo método e o número de invocação em vez disso: `Equipment can be found #2`. Um
> teste que roda uma vez mantém o nome de exibição que sempre teve, então nenhum trace aprovado
> commitado se move. O *nome de arquivo* ainda carrega o rótulo convertido em slug, porque é isso
> que distingue duas invocações em disco, e o `manifest.json` — um índice também sobre os
> artefatos que carregam valores — nomeia o cenário como o pytest o exibiu. Mantenha segredos fora
> dos ids de parametrize.

## Conteúdo

```
scenario: Weekend trip settles with three transfers

- TripSettlementService.record_expense(trip_name, expense)
  - ExpenseValidator.ensure_valid(expense)
  - TripLedger.record_expense(trip_name, expense)
- TripSettlementService.settle_trip(trip_name) → value
  - TripLedger.expenses_of(trip_name) → value
  ~ fork [2]
    - BalanceCalculator.compute_balances(expenses) → value
    - StockService.check() → value
```

- **Cabeçalho:** `scenario: <nome de teste humanizado>` + linha em branco. Nada mais — sem
  resultado, sem ids/nomes de trace, sem datas. Uma invocação de um teste que roda mais de uma vez
  é `scenario: <nome de método humanizado> #<index>` — os argumentos de um id de parametrize nunca
  chegam a ele.
- **Linha de chamada:** `NomeDaClasse.nome_do_metodo(nome_param, nome_param)` — só nomes, na
  ordem de captura, com dois espaços de indentação por nível de profundidade.
- **Tipos de desfecho:** um retorno que não é `None` renderiza ` → value`; um retorno tipo
  `None`/void: nada; uma exceção lançada ` !! NomeSimplesDaExcecao` (o tipo é estrutura; a
  mensagem é um valor e nunca aparece); uma entrada não casada ` ?? incomplete`.
- **Concorrência:** grupos fork renderizam como `~ fork [n]` e trabalho adotado a partir de um
  snapshot de contexto propagado (uma thread ou task do `asyncio` recolhendo trabalho sob um
  snapshot ativado) renderiza como `~ async [n]`, ambos com membros **ordenados por
  `Classe.metodo`** — a ordem de captura entre threads/tasks é uma escolha do scheduler, não
  comportamento, então o artefato declara o conjunto e o aninhamento do trabalho concorrente e
  nunca sua ordem. Grupos async são chaveados pelo span que os lançou, então todo filho async de
  uma chamada é um único grupo, e eles também aparecem no nível raiz quando o trabalho sobreviveu
  a quem o chamou. Trabalho fire-and-forget renderiza como `~ fire-and-forget` + filhos. Nomes/ids
  de thread nunca aparecem.
- **Excluído por design:** todos os valores de argumento/retorno, mensagens de exceção, durações,
  timestamps, identidade de thread, ids de trace/span, nomes de trace, resultados de execução, e
  narração (a narração resolvida embute valores).
- **Codificação:** UTF-8, LF, nova linha final. Identificadores passam por sanitização de
  caracteres de controle.

## Garantias

1. **Determinístico:** comportamento idêntico ⇒ arquivo idêntico byte a byte. Isso é o que faz do
   artefato a baseline do trace aprovado e o formato golden das fixtures de conformidade.
2. **Livre de valores:** zero superfície de injeção de prompt, zero PII, tokens mínimos — seguro
   para entregar a um agente de IA por padrão.
3. **Divisão de trabalho:** o artefato afirma a *forma* comportamental; a correção de valores
   continua sendo trabalho das asserções do teste. Uma mudança que só altera um valor de retorno
   com estrutura idêntica não muda o artefato — por design.

## Lacuna conhecida

Esta implementação ainda não emite o irmão JSON livre de valores que algumas outras
implementações distribuem (`<test>.structural.json`, um array no formato de `.canonical.json` com
todo valor removido) — o formato de texto `.nt` acima é o único artefato estrutural desta
implementação hoje. Registrado como trabalho futuro; `.canonical.json` (o array de entradas JSON
que carrega valores) não é afetado e continua carregando detalhe completo.

Implementado neste repositório por `narrativetrace.render.structural.StructuralTraceRenderer`,
gravado pelo plugin `narrativetrace-pytest` ao lado dos companheiros `.md`/`.json`/`.mmd` — veja o
[Guia de pytest](guia-de-pytest.md), o [Guia de configuração](guia-de-configuracao.md) e
[O que commitar](o-que-commitar.md).
