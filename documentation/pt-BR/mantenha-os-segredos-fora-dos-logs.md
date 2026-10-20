<!-- source: documentation/recipes/keep-secrets-out-of-the-logs.md blob 5343825aa6f3 | translated: 2026-10-18 | reviewed: - -->

# Mantenha os segredos fora dos logs

## O problema

> Se isto registra toda chamada com todo argumento, vai registrar um número de
> cartão. Convença-me de que não registra.

O checkout recebe uma senha e um número de cartão. Abaixo estão uma execução
dele com os dois, o log que ela realmente gravou e o teste que prova que
nenhum dos dois valores está nesse arquivo.

## Configuração mínima

Nenhuma. A ocultação está ativa em toda integração fornecida e não existe
nenhuma superfície de configuração que a desligue — a deny-list é consultada
na *captura*, antes de um valor virar evento, de modo que um valor negado nunca
chega à linha de log, ao arquivo de trace, ao caminho em buffer nem a um
consumidor dos eventos.
[Privacidade e ocultação](privacidade-e-ocultacao.md) é a versão linha a
linha, verificada contra o código.

Duas coisas, porém, valem ser feitas uma vez no seu próprio projeto:

1. **Escreva o teste desta página para o seu próprio fluxo.** Uma ocultação que
   você não afirmou é uma alegação, não uma propriedade do seu build. O achado
   do doctor "redaction never proven in a test" (`trap.redaction-proof`) existe
   exatamente para isso.
2. **Conheça a saída de emergência.** Um segredo sob um nome que ninguém
   adivinharia — `fingerprint`, `answer2` — é alcançado com
   `@not_traced("fingerprint")` no método (ou `not_traced_field(...)` em um
   campo de dataclass), que sempre vence
   ([Guia de decoradores](guia-de-decoradores.md)).

## O cenário

Um colaborador novo, para que a execução carregue uma senha além do cartão. O
parâmetro dele se chama `password` — esse nome é todo o ponto:

```python
"""Signs a customer in before the checkout charges them."""

from __future__ import annotations


class CustomerAccounts:
    """In-memory accounts. The parameter is named ``password`` -- that name is the whole point of
    documentation/recipes/keep-secrets-out-of-the-logs.md."""

    def sign_in(self, customer_id: str, password: str) -> str:
        """Returns the session id the checkout carries for the rest of the request.

        Raises ``ValueError`` when the password is blank.
        """
        if not password.strip():
            raise ValueError("password must not be blank")
        return f"SESSION-{customer_id}"
```
A execução autentica o cliente e faz o pedido. Os dois valores secretos são
constantes aqui para que o teste possa procurá-los no log depois — um fluxo
real os recebe da requisição:

```python
"""documentation/recipes/keep-secrets-out-of-the-logs.md's scenario: one checkout carrying a
password and a card number writes neither into the log its own ``logging`` setup produced -- the
password caught by its NAME, the card number by its name and again by its VALUE (rule 8, docs as
tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs it in its own pytest process and
names the log file (``NARRATIVETRACE_RECIPE_LOG``), which is the file the page embeds. The
assertion reads that file back, not a rendering this test produced: a page claiming "the secret is
not in your log" is only worth what a real log file says.
"""

import os
from pathlib import Path

from examples.recipes.checkout.accounts import CustomerAccounts
from examples.recipes.checkout.env import LOG_FILE_ENV
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, export_to_logger, trace_object

# A fixed trace id, so the page's embedded output names the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")

# Luhn-valid, like a real one -- which is what the value-shape rule recognizes.
CARD_NUMBER = "4242424242424242"

# The password this run signs in with. It matches no value-shape rule at all: only its parameter's
# NAME can save it. Named for the phrase rather than for the field it fills, because the public
# snapshot's secrets gate reads a constant whose name carries that word and whose value is a string
# literal as a credential shipped in the open -- correctly, for every such line but a documentation
# fixture's.
SIGN_IN_PASSPHRASE = "orchid-trombone-77"


def test_a_checkout_with_a_password_and_a_card_writes_neither(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    accounts = trace_object(CustomerAccounts(), narrative_trace)
    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    session = accounts.sign_in("C-1234", SIGN_IN_PASSPHRASE)
    order_id = checkout.place_order("C-1234", "SKU-KB", 2, CARD_NUMBER)

    export_to_logger(narrative_trace.capture_trace())

    assert session == "SESSION-C-1234"
    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert_neither_secret_is_in_the_log()


def assert_neither_secret_is_in_the_log() -> None:
    """The proof: the log file the project's own handler wrote, read back and searched."""
    log = Path(os.environ[LOG_FILE_ENV]).read_text(encoding="utf-8")

    assert 'CustomerAccounts.sign_in(customer_id: "C-1234", password: [REDACTED])' in log
    assert "card_number: [REDACTED]" in log
    assert "card: [REDACTED]" in log
    assert SIGN_IN_PASSPHRASE not in log
    assert CARD_NUMBER not in log
```
## A saída real

**O log que a execução gravou**, pelo logger do próprio projeto:

```text
DEBUG [solid wand romps] [narrativetrace] - → CustomerAccounts.sign_in(customer_id: "C-1234", password: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - ← returned: "SESSION-C-1234"
DEBUG [solid wand romps] [narrativetrace] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - ← returned: "PAY-C-1234-7998"
DEBUG [solid wand romps] [narrativetrace] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - ← returned: "ORD-C-1234-SKU-KB-2"
```
**O arquivo de trace da mesma execução**, que é a outra superfície que um
segredo poderia ter alcançado:

```text
---
type: trace
run: moody mouse sweeps
scenario: Test a checkout with a password and a card writes neither
entry_point: CustomerAccounts.sign_in
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 5
error_count: 0
---

## Trace: solid wand romps — CustomerAccounts.sign_in

**Scenario:** Test a checkout with a password and a card writes neither
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **CustomerAccounts.sign_in**(customer_id: `"C-1234"`, password: `[REDACTED]`) → `"SESSION-C-1234"` — 0ms #1
- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 0ms #2
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #2.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) → `"PAY-C-1234-7998"` — 0ms #2.2
  - **OrderRepository.save**(order: `Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998)`) → `null` — 0ms #2.3
  - → `"ORD-C-1234-SKU-KB-2"`
```
## Como ler

**Qual regra pegou qual valor.** Três valores sumiram, por dois mecanismos
independentes:

| Linha | Valor | Pego por |
|---|---|---|
| `#1` `CustomerAccounts.sign_in(…, password: [REDACTED])` | `orchid-trombone-77` | Seu **nome**. `password` está na deny-list sempre ativa, que casa nomes de parâmetro, nomes de campo e campos de dataclass — em vários idiomas — em qualquer classe, inclusive as suas. O valor em si não casa com padrão nenhum; nada além do nome poderia tê-lo salvado |
| `#2` `OrderService.place_order(…, card_number: [REDACTED])` | `4242424242424242` | Seu **nome** de novo: `card_number` está na mesma lista |
| `#2.2` `PaymentService.charge(…, card: [REDACTED])` | o mesmo número, uma chamada mais fundo | Seu **valor**. O parâmetro se chama `card`, que a deny-list não conhece — e o número é válido pelo Luhn, então a verificação independente de formato de valor o pegou do mesmo jeito |

A terceira linha é a que vale lembrar: `card` é como um parâmetro costuma se
chamar em código real, e só o eixo do nome o teria impresso. O eixo do formato
conhece um número de cartão válido pelo Luhn, um JWT, uma string `Set-Cookie`,
um número de Seguro Social dos EUA e os números de documento de identidade
nacionais que passam nos seus próprios checksums.

**Onde as regras vivem.** Na biblioteca, não na sua configuração:
`RedactionPolicy.DEFAULT`, consultada pelo único `ValueRenderer` que toda
integração fornecida constrói do mesmo jeito. Não existe configuração, variável
de ambiente nem nível de log que a alcance;
[Privacidade e ocultação](privacidade-e-ocultacao.md) lista tanto as
superfícies quanto o que prevalece sobre o quê. Aliás, `customer_id: "C-1234"`
*é* gravado por inteiro — um id de cliente é identificador, não segredo, e o
NarrativeTrace não adivinha. Se o seu não deve ser registrado, isso é
`@not_traced`, que é uma decisão no seu código-fonte e não um estado que um
deploy possa alternar.

**Por que o teste é a prova, e não a página.** As últimas linhas do cenário
leem o arquivo que o handler gravou e afirmam duas coisas: que os parâmetros
ocultados estão presentes *como* `[REDACTED]`, e que nenhuma das duas strings
secretas aparece em lugar algum dele. Uma página só pode lhe mostrar bytes; um
teste quebra o build no dia em que uma refatoração renomeia `password` para
algo que a lista não conhece, ou alguém constrói o próprio `ValueRenderer` com
`RedactionPolicy.DISABLED`. Essa é a diferença entre "estava seguro quando isto
foi escrito" e "está seguro agora". Mantenha as asserções de ausência — as
`not in` — mesmo quando as de presença parecerem suficientes: um valor que some
porque a chamada deixou de ser rastreada ainda satisfaria a primeira.

## O que não é capturado

- **Código que não é rastreado não é do NarrativeTrace para ocultar.** Cinco
  objetos são envolvidos acima; um segredo passado entre duas classes não
  envolvidas não é visto e, portanto, não é nem ocultado nem registrado. Isso
  não é garantia de segurança — é garantia de silêncio.
- **Um segredo que a sua própria instrução de log escreve é problema seu.** O
  NarrativeTrace oculta o que *ele* renderiza.
  `logger.info("charging %s", card_number)` é a sua linha, no seu código, e nada
  aqui a filtra. O contrato de ocultação trata da narrativa gerada, não de tudo
  o que o processo escreve.
- **Um valor de retorno não é casado por nome**, porque não tem nenhum.
  `sign_in` retorna `"SESSION-C-1234"` e ele é impresso. Um token de sessão
  retornado por um método rastreado precisa que as regras de formato o peguem,
  ou `@not_traced` no método, ou um tipo de retorno mais estreito.
- **Nomes que a lista não conhece.** A lista é grande e multilíngue, não
  infinita. Um segredo chamado `q3` só é pego pelo seu formato, se tiver um.
  Afirme, não presuma — que é todo o ponto desta página.
- **O que acontece depois que a linha de log é gravada.** Envio, retenção e
  acesso ao arquivo são da sua plataforma; o `.nt` estrutural não carrega valor
  algum e é o artefato feito para ser commitado e entregue a um modelo
  ([Revise um fluxo complexo antes de alterá-lo](revise-um-fluxo-complexo-antes-de-altera-lo.md)).

**A skill para isto:** `narrativetrace-doctor` — uma das suas verificações é
exatamente "redaction never proven in a test", e ela indica a correção.
