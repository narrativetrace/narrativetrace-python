<!-- source: documentation/recipes/trace-in-production-without-the-cost.md blob 36e9d5a351e8 | translated: 2026-10-18 | reviewed: - -->

# Trace em produção sem o custo

## O problema

> Quero isto em produção para as requisições que dão errado. Não quero pagar
> por um trace completo de cada requisição que dá certo.

Isso é uma única configuração — o nível de tracing — e esta página é a mesma
execução vista através dele duas vezes: o checkout com pagamento recusado em
`DETAIL`, onde todo valor é capturado, e em `ERRORS`, onde só sobrevivem as
execuções que falharam.

## Configuração mínima

Um nível, definido onde quer que o seu deploy seja configurado. Os dois abaixo
dizem a mesma coisa:

```toml
# narrativetrace.toml (or [tool.narrativetrace] in pyproject.toml, never both)
level = "ERRORS"   # "OFF" | "ERRORS" | "SUMMARY" | "NARRATIVE" | "DETAIL"
```

```bash
# or in the environment, which wins over the file
NARRATIVETRACE_LEVEL=ERRORS uv run pytest
```

Em código, é `ContextVarNarrativeContext(NarrativeTraceConfig(level=TracingLevel.ERRORS))`
([Guia de configuração, nível de tracing](guia-de-configuracao.md#tracing-level)).

O nível é o botão do próprio NarrativeTrace e fica na frente de tudo: uma
chamada que ele filtra nunca vira evento, para nenhum consumidor. O nível do seu
logger é um segundo botão, independente, que decide o que é *impresso* —
[FAQ, "Two dials, two paths"](../faq.md#two-dials-two-paths) é a versão longa,
e a distinção importa aqui porque subir o nível de um logger economiza volume
de log sem mudar nada na captura.

## O cenário

A execução é a reprodução do pagamento recusado de
[Ajude-me a depurar e corrigir este bug](ajude-me-a-depurar-e-corrigir-este-bug.md)
— `reserve`, depois `charge` lançando exceção, depois `release` — reaproveitada
sem alterações, porque o assunto desta página é o botão e não outro fluxo. O
driver abaixo a executa nos dois níveis, e executa também um checkout
*bem-sucedido* nos dois:

```python
def _cost() -> dict[str, Run]:
    """The declined-payment reproduction at both levels, and a checkout that succeeds at both."""
    declined = "test_the_stock_is_released_when_the_card_is_declined"
    return {
        "cost_detail": _at_level("detail", "declined_payment", declined),
        "cost_errors": _at_level("errors", "declined_payment", declined, level="ERRORS"),
        "cost_detail_successful": _at_level("detail-successful", "checkout_review"),
        "cost_errors_successful": _at_level("errors-successful", "checkout_review", level="ERRORS"),
    }


def _at_level(directory: str, module: str, test: str | None = None, level: str = "DETAIL") -> Run:
    """One fixture run into its own directory, at ``level`` (the default level is DETAIL)."""
    return _run_fixture(module, _settings(COST, directory, NARRATIVETRACE_LEVEL=level), test)
```

Cada chamada é um processo pytest real com o `narrativetrace-pytest` carregado,
em um diretório próprio, com `NARRATIVETRACE_LEVEL` definido do jeito que um
deploy definiria.

## A saída real

**Em `DETAIL`**, a execução recusada, com todos os valores capturados:

```text
---
type: trace
run: jumpy brick arcs
scenario: Test the stock is released when the card is declined
entry_point: OrderService.place_order
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 4
error_count: 2
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test the stock is released when the card is declined
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) #1.2

    > ❌ `PaymentDeclinedError`: card declined by the issuer — 0ms
  - **InventoryService.release**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.3
  - ❌ `PaymentDeclinedError`: card declined by the issuer
```

**Em `ERRORS`**, a mesma execução do mesmo código:

```text
---
type: trace
run: limp pond mixes
scenario: Test the stock is released when the card is declined
entry_point: OrderService.place_order
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 4
error_count: 2
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test the stock is released when the card is declined
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: ``, sku: ``, quantity: ``, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: ``, quantity: ``) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: ``, amount_cents: ``, card: ``) #1.2

    > ❌ `PaymentDeclinedError`: card declined by the issuer — 0ms
  - **InventoryService.release**(sku: ``, quantity: ``) → `null` — 0ms #1.3
  - ❌ `PaymentDeclinedError`: card declined by the issuer
```

**E em `ERRORS`, um checkout que deu certo**: nenhum artefato. Não há nada para
embutir, e esse é justamente o ponto — os testes de receita deste repositório
afirmam as duas metades dessa alegação, a ausência do arquivo em `ERRORS` e a
sua presença em `DETAIL`, de modo que o vazio é obra do nível e não de um
caminho que nunca esteve certo.

## Como ler

- **O que o `ERRORS` mantém.** A execução que falhou, inteira. `#1` lançou
  exceção, e a subárvore de um nó de erro é mantida intacta — então `reserve`
  (`#1.1`), `charge` (`#1.2`) e `release` (`#1.3`) continuam todos lá, inclusive
  as duas chamadas que retornaram normalmente. Isso é deliberado: as chamadas
  ao redor de uma falha são o que você precisa para diagnosticá-la, e descartar
  a irmã bem-sucedida deixaria você com uma exceção e sem história. Uma chamada
  que retornou *e* não leva a nenhuma falha abaixo dela é descartada, e uma raiz
  sem nenhuma falha em toda a sua subárvore é descartada por completo — por isso
  o checkout bem-sucedido não gravou nada.
- **O que o `ERRORS` descarta.** Todo valor de parâmetro: onde o `DETAIL`
  imprimiu `customer_id: "C-1234"` em um trecho de código, o `ERRORS` imprime
  `customer_id:` e um trecho de código vazio. O valor nunca foi renderizado,
  então não pode ser recuperado depois a partir desses eventos, em nenhum nível
  posterior. O que sobrevive é a forma, os resultados (`reserve` e `release`
  ainda dizem `→ null`) e a exceção, e `card_number` ainda mostra `[REDACTED]`
  porque a ocultação é uma decisão diferente da supressão.
- **A poda acontece depois da captura, não no lugar dela.** Toda chamada foi
  interceptada e todo evento foi publicado; só então a árvore é construída e o
  que o nível não mantém é removido. Essa é a forma honesta do custo: o `ERRORS`
  é mais barato que o `DETAIL` porque os valores não são renderizados — a parte
  cara —, não porque as chamadas deixam de ser interceptadas.
- **Só o `OFF` pula a interceptação.** Em `OFF`, a verificação de
  `context.is_active()` do wrapper retorna antes que qualquer captura, evento ou
  publicação aconteça, e nada adiante pode trazer a chamada de volta — um teste
  neste repositório afirma que uma chamada em `OFF` deixa o trace capturado
  vazio. `ERRORS`, `SUMMARY` e `NARRATIVE` ainda interceptam toda chamada. Se a
  pergunta é "quanto o tracing custa neste laço quente", a resposta é um nível
  diferente para esse escopo, ou `OFF`.
- **Os números.** Não há nenhum para citar, e esta página não digita nenhum: a
  [seção Performance do README](../../README.md#performance) diz o que a suíte
  de benchmarks mede e que ainda não há números oficiais publicados, e é lá que
  qualquer número vai aparecer quando houver um. Uma cópia que acompanha as
  medições vale mais que duas que discordam.

## O que não é capturado

- **Não há números publicados em que se apoiar.** Meça o nível que você pretende
  usar: o seu interpretador, o seu hardware, o formato dos seus parâmetros (um
  grafo de objetos profundo leva mais tempo para ser renderizado do que um
  `int`) e quanto do seu código é rastreado, tudo isso move a resposta.
- **Um nível não é um controle de privacidade.** O `ERRORS` escreve menos
  valores por acaso, porque os suprime, mas supressão e ocultação são mecanismos
  diferentes, com garantias diferentes:
  [Mantenha os segredos fora dos logs](mantenha-os-segredos-fora-dos-logs.md) é
  o que vale em todos os níveis.
- **Nada aqui muda quanto o seu logger escreve.** Cada evento capturado ainda é
  oferecido à ponte de logging, então o nível do próprio logger `narrativetrace`
  é o que decide o volume de log. Dois botões.
- **Um nível não pode ser subido retroativamente.** Valores não capturados
  estão perdidos; reproduzir a execução em `DETAIL` é o único caminho de volta,
  que é o que a receita de depuração faz.
- **Níveis por escopo não aparecem aqui.** Esta página define um único nível
  para a execução inteira. Estreitar o escopo rastreado — quais objetos são
  envolvidos, afinal — é a outra metade da questão do custo, e pertence a
  [Escolhendo uma integração](escolhendo-uma-integracao.md).

**A skill para isto:** `narrativetrace-doctor` — ela informa o nível em que um
projeto está realmente rodando, que é a primeira coisa a conferir quando um
trace está mais magro do que o esperado.
