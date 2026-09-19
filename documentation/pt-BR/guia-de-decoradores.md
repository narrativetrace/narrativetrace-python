<!-- source: documentation/guides/decorators.md blob c4f5e00e06e9 | translated: 2026-09-17 | reviewed: - -->

# Decoradores

Envolver um objeto com `trace_object` traça cada método público. Decoradores refinam o que é
capturado e como isso é narrado.

## Você importou isso — é assim que se aplica

Importar `narrated` ou `not_traced` não faz nada por si só — cada um precisa ser aplicado a um
método ou parâmetro real, e o resultado precisa ser provado com uma asserção. O par mínimo dos
dois, empilhados em um único método do jeito que `AuthService` já faz em
`packages/narrativetrace/tests/test_trace_object.py`:

```python
from narrativetrace import (
    ContextVarNarrativeContext,
    ProseRenderer,
    narrated,
    not_traced,
    trace_object,
)


class AuthService:
    @narrated("login attempt for {username} with {password}")
    @not_traced("password")
    def login(self, username: str, password: str) -> str:
        return f"session-for-{username}"


def run() -> str:
    """Traces one login and renders the result -- `password` never reaches it, in the argument
    list or in the narration template that names it."""
    context = ContextVarNarrativeContext()
    service = trace_object(AuthService(), context)
    service.login("alice", "hunter2")
    return ProseRenderer().render(context.capture_trace())
```

```text
The trace damp shard sways:

The auth service login — login attempt for alice with [REDACTED], returning "session-for-alice".
```

A asserção que prova isso: `assert "[REDACTED]" in rendered` — `password` nunca chega ao texto de
narração que `@narrated` constrói ao redor dele, e uma asserção vizinha verifica que `username`, o
argumento não ocultado, ainda está presente (`examples/test_import_and_use.py`).

`uv run narrativetrace doctor` observa exatamente essa falha no código-fonte de um projeto:
**`trap.silent-sink`** sinaliza as superfícies de ocultação de campo abaixo (`not_traced_field`,
`__nt_not_traced__`) importadas ou declaradas mas nunca realmente aplicadas — chame
`not_traced_field(...)` em um campo real ou liste nomes de campo reais em `__nt_not_traced__`, e
depois prove isso asseverando `"[REDACTED]"` em um trace renderizado — e **`trap.redaction-proof`**
sinaliza um projeto sem nenhum teste que assevere o marcador literal `[REDACTED]`. Os dois
decoradores, e as duas superfícies de ocultação de campo, em detalhe a seguir.

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
- **Um `__str__` personalizado nunca é confiável para os seus próprios tipos** *(since 0.1.2)*.
  Qualquer objeto que carregue estado de instância — uma dataclass, uma classe attrs, um
  `NamedTuple`, ou um objeto simples com `__dict__`/`__slots__` preenchido — é introspectado campo
  a campo independente de também definir `__str__`/`__repr__`; esse método escrito à mão nunca é
  consultado, do mesmo jeito que nunca era consultado numa dataclass. Antes dessa correção, o
  `__str__` personalizado de uma classe simples prevalecia sobre a introspecção assim que era
  definido, então um `__str__` escrito à mão que interpolasse um campo sensível — diretamente, ou
  transitivamente através do `__str__` de um objeto aninhado — driblava a ocultação por completo;
  uma chave de dict/map tinha exatamente a mesma brecha (um `str(key)` nu e sem mediação), agora
  fechada da mesma forma: uma chave é introspectada e verificada contra a ocultação exatamente como
  um valor. Dê a um composto um método `@narrative_summary` quando você quiser um resumo curado de
  uma linha em vez do padrão campo a campo — esse mecanismo não é afetado e continua sendo a forma
  suportada de controlar exatamente o que é mostrado.
- **Não declarar nenhum campo também não conquista confiança** *(since 0.1.3, unreleased)*. Um
  valor cujo estado a introspecção não consegue ver — uma subclasse de `ctypes.Structure` ou um
  tipo de extensão que guarda seus campos em uma struct C, uma classe que guarda seu estado em uma
  tabela de nível de módulo indexada por identidade ou em um closure — contava como folha e era
  renderizado pelo próprio `__str__`/`__repr__`, que podia imprimir esses campos passando pela
  lista de negação. Agora ele é renderizado apenas como o nome do seu tipo
  (`<CStructCredentials>`): presente, limitado, não lido. Os próprios tipos de valor da biblioteca
  padrão (`pathlib.Path`, `datetime`, `uuid.UUID`, `decimal.Decimal`, um membro de `Enum`, …)
  continuam sendo renderizados pelo seu próprio texto curto — essa confiança é decidida pela
  origem, e por nada mais.
- **Um resumo, `__str__` ou getter que lança exceção renderiza um marcador de erro tipado, nunca
  sua própria mensagem** *(since 0.1.2)*. `<error: ValueError>`, `<error: RecursionError>`, e assim por diante — o
  nome do próprio TIPO da exceção da parte que falha, substituído só para aquela parte (nunca o
  trace inteiro, nunca um `<error>` nu). A *mensagem* da exceção deliberadamente nunca é
  renderizada: uma mensagem pode carregar o próprio valor que falhou ao renderizar
  (`"summary failed for {token}"` vazaria `token` de outra forma), então só o nome do tipo — nunca
  `str(exc)` — chega à saída.
- **Uma coleção só é enumerada quando é definida pela plataforma.** `list`/`tuple`/`dict`/`set`/
  `frozenset` são enumeradas através do seu próprio estado; uma subclasse de uma delas é
  enumerada através da própria leitura de estado desse ancestral, nunca do `__iter__`/`items`
  sobrescrito da subclasse. Uma coleção feita à mão (implementando o protocolo `Collection` do
  zero, sem ancestral de plataforma) também não é enumerada — ela é renderizada como um objeto
  comum, campo a campo. Um iterável simples que não é um `Collection` completo (sem
  `__contains__`) é renderizado como seu nome de tipo mais o tamanho, nunca seus elementos, e seu
  `__iter__` nunca é tocado. A única exceção é o gancho `__narrative_elements__` abaixo.
- **`__narrative_elements__` é o único gancho confiável para enumerar seus próprios
  elementos.** Definido em mais detalhe abaixo.
- **A invocação é limitada e isolada.** A saída tem limite (tamanho de string, itens de coleção,
  profundidade); um `__str__`, resumo ou getter que lança exceção nunca consegue falhar a chamada de
  negócio traçada (templates recorrem ao marcador literal `{placeholder}`); os valores são
  renderizados de forma antecipada no ponto da chamada, então qualquer efeito colateral acontece uma
  única vez, em um ponto determinístico. Futures e awaitables nunca são forçados.

## `__narrative_elements__` — iteração confiável

O terceiro gancho de renderização sancionado, ao lado de `@narrative_summary` e do próprio
`__str__` de um valor da plataforma: um tipo que declara um método `__narrative_elements__` sem
argumentos é confiável para enumerar seus próprios elementos através desse método — o único caso
em que a renderização executa a própria iteração de um tipo, porque quem o escreveu a declarou
pura.

```python
class OrderLine:
    def __init__(self, items: list[Item]) -> None:
        self._items = items

    def __narrative_elements__(self) -> list[Item]:
        return list(self._items)
```

Um `OrderLine` renderizado mostra seus itens (com o mesmo limite de itens de uma coleção comum,
com o mesmo marcador `… (N total)` ao ultrapassá-lo) em vez do nome do campo `_items`. O método
roda sob a mesma proteção reflexiva de renderização que qualquer outro gancho: uma chamada que
ele faça a um objeto traçado não abre span nenhum próprio. Um `__narrative_elements__` que lança
exceção degrada para o mesmo marcador tipado `<error: TypeName>` que qualquer outra falha de
gancho, nunca para os campos reais do objeto.

Use-o quando um tipo de coleção feito à mão (um sem ancestral de plataforma para recorrer, que de
outra forma seria renderizado como um objeto comum) tiver elementos que valha a pena mostrar
diretamente — o mesmo papel que `@NarrativeElements` cumpre nos demais runtimes do
NarrativeTrace.

Se um membro não pode ser puro, marque-o com `@not_traced` / `not_traced_field(...)` — o valor de um
membro oculto nunca é lido de forma alguma — ou dê ao tipo um `@narrative_summary` para que você
controle exatamente o que é acessado (um `__str__` cuidadosamente escrito não tira mais um composto
da introspecção, veja acima). Em `NARRATIVETRACE_LEVEL=OFF` (e para valores de parâmetro em
`SUMMARY`), nenhuma renderização de argumentos acontece.
