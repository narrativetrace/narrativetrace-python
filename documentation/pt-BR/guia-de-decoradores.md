<!-- source: documentation/guides/decorators.md blob 6f260cb42c31 | translated: 2026-09-12 | reviewed: - -->

# Decoradores

Envolver um objeto com `trace_object` traça cada método público. Decoradores refinam o que é
capturado e como isso é narrado.

## `@narrated` — narração em prosa

```python
from narrativetrace import narrated

class InventoryService:
    @narrated("reserves {quantity} of {product_id}")
    def reserve(self, product_id: str, quantity: int) -> Reservation:
        ...
```

Os tokens de template `{name}` e um nível com ponto `{customer.address}` são resolvidos a partir dos
valores dos parâmetros; um caminho mais profundo como `{customer.address.city}` nunca pode ser
resolvido e sobrevive literalmente em tempo de execução, então um marcador que o nomeia ainda assim
emite um aviso de token não resolvido na suíte.

**A ocultação prevalece sobre um template que a nomeia.** Um caminho que alcança um membro oculto —
em qualquer profundidade do caminho, não só no último segmento — resolve para `[REDACTED]` em vez do
valor ou do marcador literal. Um `{nome}` simples que nomeia um valor diretamente obedece às mesmas
duas regras: a lista de negação lê essa chave exatamente como lê um nome de campo, e a forma do
próprio valor também é verificada, então `@narrated("login {password}")` e um JWT chegando como
`{value}` ambos renderizam `[REDACTED]`. Nomear um caminho, ou um valor, nunca enfraquece as regras
que se aplicam ao valor diretamente: se você precisa do valor em uma narrativa, remova `@not_traced`
do membro; essa remoção
é a decisão deliberada e revisável, e aparece no diff.

## `@on_error` — contexto de falha

Empilhável; anexa uma mensagem resolvida a uma saída com falha para o tipo de exceção
correspondente:

```python
from narrativetrace import on_error

class PaymentService:
    @on_error(TimeoutError, "gateway timed out charging {customer_id}")
    def charge(self, customer_id: str, amount: int) -> Payment:
        ...
```

## `@not_traced` — ocultação

Oculte um parâmetro pelo nome:

```python
from narrativetrace import not_traced

class AuthService:
    @not_traced("password")
    def login(self, username: str, password: str) -> Session:
        ...
```

Oculte um **campo** de um objeto passado como argumento, de duas formas:

- **`not_traced_field(...)`** — um campo de dataclass, marcado pelos próprios metadados do seu
  `field()`.
- **`__nt_not_traced__`** — um atributo de classe que nomeia os campos a ocultar, para qualquer
  outro tipo de objeto: uma classe simples, um `NamedTuple`, ou uma classe attrs, onde quer que
  `field(metadata=...)` não esteja disponível. É uma tupla/lista/conjunto de nomes de campo lida da
  **classe** (`is_field_not_traced` a verifica antes dos metadados de dataclass), então subclasses
  a herdam e instâncias não podem sobrescrevê-la.

Ambas ocultam de forma idêntica — campo a campo, não o objeto contêiner inteiro — e prevalecem
incondicionalmente sobre qualquer política:

```python
from dataclasses import dataclass

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    not_traced_field,
    trace_object,
)


@dataclass
class Credentials:
    username: str
    secret: str = not_traced_field(default="")


class LegacyCredentials:
    """A plain (non-dataclass) class: `__nt_not_traced__` names the fields to redact."""

    __nt_not_traced__ = ("secret",)

    def __init__(self, username: str, secret: str) -> None:
        self.username = username
        self.secret = secret


class AuthService:
    # Parameter named `account`, not `credentials` -- the latter is itself on the name-based
    # deny-list (see documentation/privacy-and-redaction.md) and would redact the whole argument
    # regardless of which fields inside it are marked `@not_traced`.
    def login(self, account: Credentials | LegacyCredentials) -> str:
        return f"session-for-{account.username}"


def run() -> str:
    """Traces two logins, one per redaction surface, and renders the result."""
    context = ContextVarNarrativeContext()
    service = trace_object(AuthService(), context)
    service.login(Credentials("alice", "hunter2"))
    service.login(LegacyCredentials("bob", "hunter2"))
    return IndentedTextRenderer().render(context.capture_trace())
```

`python -m examples.not_traced_fields` imprime (`0ms` varia conforme a máquina, igual à página de
60 segundos):

```text
AuthService.login(account: Credentials(username="alice", secret=[REDACTED])) → "session-for-alice" — 0ms
AuthService.login(account: LegacyCredentials(username="bob", secret=[REDACTED])) → "session-for-bob" — 0ms
```

Valores ocultos são substituídos por um marcador antes da renderização — nunca chegam a um
renderizador, exportador ou log.

## O contrato de pureza — efeitos colaterais durante o tracing

O NarrativeTrace pode invocar um conjunto pequeno e fixo de caminhos de código nos seus objetos
enquanto renderiza um trace. Mantenha esses membros **puros** — livres de efeitos colaterais como
carregamento preguiçoso, contadores de acesso, preenchimento de cache ou I/O — exatamente como você
faria para um depurador ou um serializador.

O que é invocado, e o que não é:

- **A introspecção enumera dados armazenados, não código.** Nomes de campo vêm de
  `dataclasses.fields()`, metadados do attrs, o `_fields` de um `NamedTuple`, ou o
  `__dict__`/`__slots__` da instância — então uma `@property` calculada (cujo getter poderia contar
  acessos ou carregar de forma preguiçosa) nunca é enumerada nem executada durante a introspecção.
  Um `NamedTuple` é introspectado pelo nome do campo em vez de renderizado como uma lista anônima de
  valores posicionais, então um campo oculto permanece oculto da mesma forma que um campo de
  dataclass.
- **Um `__str__` personalizado só é confiável para uma folha genuína** *(since 0.1.2,
  unreleased)*. Qualquer objeto que carregue estado de instância — uma dataclass, uma classe attrs, um
  `NamedTuple`, ou um objeto simples com `__dict__`/`__slots__` preenchido — é introspectado campo
  a campo independente de também definir `__str__`/`__repr__`; esse método escrito à mão nunca é
  consultado, do mesmo jeito que nunca era consultado numa dataclass. Só um valor sem nenhum estado
  de instância (um número, uma string, uma classe auxiliar sem estado, um membro de `Enum` sem
  payload) ainda é renderizado pelo seu próprio `str()`. Antes dessa correção, o `__str__`
  personalizado de uma classe simples prevalecia sobre a introspecção assim que era definido, então
  um `__str__` escrito à mão que interpolasse um campo sensível — diretamente, ou transitivamente
  através do `__str__` de um objeto aninhado — driblava a ocultação por completo; uma chave de
  dict/map tinha exatamente a mesma brecha (um `str(key)` nu e sem mediação), agora fechada da mesma
  forma: uma chave é introspectada e verificada contra a ocultação exatamente como um valor. Dê a um
  composto um método `@narrative_summary` quando você quiser um resumo curado de uma linha em vez do
  padrão campo a campo — esse mecanismo não é afetado e continua sendo a forma suportada de
  controlar exatamente o que é mostrado.
- **Um resumo, `__str__` ou getter que lança exceção renderiza um marcador de erro tipado, nunca
  sua própria mensagem** *(since 0.1.2, unreleased)*. `<error: ValueError>`, `<error: RecursionError>`, e assim por diante — o
  nome do próprio TIPO da exceção da parte que falha, substituído só para aquela parte (nunca o
  trace inteiro, nunca um `<error>` nu). A *mensagem* da exceção deliberadamente nunca é
  renderizada: uma mensagem pode carregar o próprio valor que falhou ao renderizar
  (`"summary failed for {token}"` vazaria `token` de outra forma), então só o nome do tipo — nunca
  `str(exc)` — chega à saída.
- **A invocação é limitada e isolada.** A saída tem limite (tamanho de string, itens de coleção,
  profundidade); um `__str__`, resumo ou getter que lança exceção nunca consegue falhar a chamada de
  negócio traçada (templates recorrem ao marcador literal `{placeholder}`); os valores são
  renderizados de forma antecipada no ponto da chamada, então qualquer efeito colateral acontece uma
  única vez, em um ponto determinístico. Futures e awaitables nunca são forçados.

Se um membro não pode ser puro, marque-o com `@not_traced` / `not_traced_field(...)` — o valor de um
membro oculto nunca é lido de forma alguma — ou dê ao tipo um `@narrative_summary` para que você
controle exatamente o que é acessado (um `__str__` cuidadosamente escrito não tira mais um composto
da introspecção, veja acima). Em `NARRATIVETRACE_LEVEL=OFF` (e para valores de parâmetro em
`SUMMARY`), nenhuma renderização de argumentos acontece.
