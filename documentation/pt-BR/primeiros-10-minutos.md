<!-- source: documentation/first-10-minutes.md blob 5d7e0ca81bf6 | translated: 2026-09-09 | reviewed: 2026-09-09 -->

# Primeiros 10 minutos

Um serviço minúsculo, um teste pytest, sete passos. Cada comando abaixo foi executado de verdade contra esta
versão do repositório — os caminhos de arquivo, as pontuações de clareza e o marcador `[REDACTED]` são
saída real, não ilustrações. As únicas coisas que vão diferir na sua máquina são a
duração (`ms`), o `trace_id` hexadecimal aleatório e o `trace_name` de três palavras — os três
gerados na hora a cada execução.

Python ≥ 3.12. Se você ainda não rodou a demo, `uv run poe demo --example ecommerce --no-pause`
a partir da raiz do repositório é ainda mais rápido — esta página é para quando você quer ver o resultado contra o
*seu próprio* código.

## 1. Instale o plugin do pytest

```bash
uv add --dev narrativetrace-pytest
```

Essa é toda a configuração de dependências: o plugin já traz o core, `narrativetrace-diagrams` e
`narrativetrace-clarity` (o passo 6 abaixo usa seu script de console), e se registra no pytest
automaticamente por um entry point — nada para adicionar ao `conftest.py`.

## 2. Adicione um serviço

```python
# order_service.py
class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"
```

Sem interface, sem classe base, sem registro. `trace_object` envolve diretamente qualquer objeto concreto.

## 3. Adicione um teste

```python
# test_order_service.py
from narrativetrace import trace_object

from order_service import OrderService


class TestOrderService:
    def test_customer_places_order(self, narrative_trace):
        service = trace_object(OrderService(), narrative_trace)
        service.place_order("C-1234", "SKU-KB", 2)
```

`narrative_trace` é uma fixture — solicite-a e você recebe um contexto de captura novo, encerrado (e,
com a saída habilitada, gravado em disco) ao final do teste.

## 4. Rode a suíte

```bash
NARRATIVETRACE_OUTPUT=1 uv run pytest -s
```

```text
.Scenario: Test customer places order

Execution trace:
OrderService.place_order(customer_id: "C-1234", product_id: "SKU-KB", quantity: 2) → "ORD-C-1234-SKU-KB-2" — 0ms
Trace written: narrative-traces/traces/TestOrderService/test_customer_places_order.md


NarrativeTrace — Suite complete
  1 scenarios recorded
  Clarity: 100% high | 0% moderate | 0% low
  Reports: narrative-traces
1 passed in 1.00s
```

> O eco "Execution trace" por teste é uma saída padrão comum, e a captura padrão do pytest
> a esconde a menos que você passe `-s` (ou o teste falhe). O resumo final da suíte sempre é impresso — ele passa
> pelo hook terminal-summary do pytest, que ignora a captura. Veja
> [Solução de problemas](solucao-de-problemas.md).

## 5. Abra a narrativa

`narrative-traces/traces/TestOrderService/test_customer_places_order.md`:

```markdown
---
type: trace
scenario: Test customer places order
entry_point: OrderService.place_order
duration_ms: 0
trace_id: aa4ae2eaa56e7e49b7aa42aece5999f0
trace_name: muted stone tests
method_count: 1
error_count: 0
---

## Trace: OrderService.place_order

**Scenario:** Test customer places order
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, product_id: `"SKU-KB"`, quantity: `2`) → `"ORD-C-1234-SKU-KB-2"` — 0ms
```

Cada valor no fluxo de chamadas — os valores dos parâmetros, o valor de retorno — veio da chamada que você
realmente fez. Nada foi escrito à mão. `duration_ms: 0` também é real: essa chamada rodou em menos de um
milissegundo, e é mostrada como número inteiro, não escondida.

## 6. Renomeie `place_order` para `process` e veja a clareza cair

A qualidade dos nomes é medida, não afirmada. O scanner independente (o mesmo que o `poe check` conecta
ao gate deste próprio repositório) lê o código-fonte diretamente, sem precisar rodar testes:

```bash
uv run narrativetrace-clarity order_service.py --min-score 0.5 --max-high-issues 0 --output-dir clarity-out
```

```text
Clarity analysis complete: 1 classes scanned
Output: clarity-out
```

`clarity-out/clarity-report.md`:

```markdown
| Scenario | Score |
|----------|-------|
| OrderService | 0.89 |
```

Renomeie o método (a definição e o local da chamada) para `process` e rode o scanner de novo com um
limiar que bloquearia um job real de CI:

```bash
uv run narrativetrace-clarity order_service.py --min-score 0.8 --max-high-issues 0 --output-dir clarity-out
```

```text
OrderService: overall 0.68 below --min-score 0.80
1 HIGH-severity issues exceed --max-high-issues 0
Clarity analysis complete: 1 classes scanned
Output: clarity-out
```

Agora o comando sai com código `1`. `clarity-out/clarity-report.md` mostra exatamente por quê:

```markdown
### OrderService

## Scores

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Method Names | 0.10 | 0.30 | 0.03 |
| Class Names | 0.91 | 0.20 | 0.18 |
| Parameter Names | 0.92 | 0.25 | 0.23 |
| Structural | 1.00 | 0.15 | 0.15 |
| Cohesion | 0.90 | 0.10 | 0.09 |
| **Overall** | **0.68** | | |

| Severity | Category | Element | Suggestion |
|----------|----------|---------|------------|
| HIGH | method-name | `OrderService.process` | Use a domain-specific verb+noun (e.g., calculateTotal, reserveInventory) |
```

Mesma chamada, mesmos valores, tudo igual exceto o nome — a pontuação geral caiu de 0.89 para 0.68,
só a dimensão de nomes de método caiu de 0.81 para 0.10, e apareceu um problema de severidade HIGH com uma
sugestão concreta. Veja o [Guia de clareza](guia-de-clareza.md) para o modelo de pontuação completo. Renomeie
de volta para `place_order` (ou para algo ainda mais específico) antes de continuar.

## 7. Adicione `@not_traced` e veja a ocultação

```python
from narrativetrace import not_traced, trace_object


class OrderService:
    @not_traced("payment_token")
    def place_order(self, customer_id, product_id, quantity, payment_token):
        return f"ORD-{customer_id}-{product_id}-{quantity}"
```

Passe um token no teste (`service.place_order("C-1234", "SKU-KB", 2, "tok_live_51H8x9J")`) e rode
de novo. O trace:

```text
- **OrderService.place_order**(customer_id: `"C-1234"`, product_id: `"SKU-KB"`, quantity: `2`, payment_token: `[REDACTED]`) → `"ORD-C-1234-SKU-KB-2"` — 0ms
```

O nome do parâmetro ainda aparece — você consegue ver que um token *foi* passado — mas seu valor nunca chega
ao disco. Veja [Privacidade e ocultação](privacidade-e-ocultacao.md) para saber o que mais a ocultação cobre e a
única forma documentada de restringi-la.

## Para onde ir agora

| Você quer | Vá para |
|---|---|
| Um caminho de integração diferente da fixture do pytest acima | [Escolhendo uma integração](escolhendo-uma-integracao.md) |
| O contrato de privacidade linha por linha | [Privacidade e ocultação](privacidade-e-ocultacao.md) |
| Quais arquivos gerados commitar | [O que commitar](o-que-commitar.md) |
| Algo acima não funcionou como mostrado | [Solução de problemas](solucao-de-problemas.md) |
| Cada opção de configuração | [Guia de configuração](guia-de-configuracao.md) |
