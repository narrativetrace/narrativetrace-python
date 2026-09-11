<!-- source: documentation/troubleshooting.md blob 1839b50194fe | translated: 2026-09-11 | reviewed: - -->

# Solução de problemas

Sintoma → causa → correção, para os modos de falha que as pessoas realmente encontram. Algumas
entradas são a explicação completa; outras apontam para o guia que já traz mais detalhe em vez de
repeti-lo aqui — um único lugar por fato.

## Nenhum arquivo de saída de trace

**Causa:** a saída de artefatos vem ligada por padrão, então algo a desligou — um
`NARRATIVETRACE_OUTPUT=false` no ambiente ou na CI, ou `output = false` em `narrativetrace.toml` /
na tabela `[tool.narrativetrace]` do `pyproject.toml` — ou os arquivos estão em um diretório
diferente do que você está olhando.

**Correção:** remova a desativação e confira `NARRATIVETRACE_OUTPUT_DIR` (padrão:
`narrative-traces/` sob o rootdir do pytest) — veja o [Guia de configuração](guia-de-configuracao.md).
Um trace vazio (um objeto envolvido cujos métodos nunca foram chamados) não grava nada mesmo com a
saída habilitada; não há arquivo vazio para encontrar.

## Não vejo o trace por teste no meu terminal

**Causa:** o eco "Execution trace" por teste é escrito com um `print()` simples, e o pytest captura a
saída padrão por padrão — uma execução simples de `pytest` não mostra nada no seu terminal mesmo que
o arquivo sob `narrative-traces/` tenha sido gravado corretamente.

**Correção:** rode com `-s` (`pytest -s`) para ver ao vivo, ou verifique o arquivo diretamente. O
resumo de rodapé da suíte (`NarrativeTrace — Suite complete …`) sempre é impresso, independente
disso, porque passa pelo hook `pytest_terminal_summary` do pytest, que ignora a captura.

## Os parâmetros de um método com `*args` aparecem como um único valor `args: [...]`

**Causa:** `inspect.signature` consegue vincular nomes de parâmetro para uma assinatura comum, mas um
método que recebe `*args` não tem nomes por argumento para ler — não há nada nomeado para
reconstruir que o próprio Python não tenha.

**Correção:** adicione `@traced("first", "second", ...)` para fornecer os nomes explicitamente:

```python
from narrativetrace import traced

class Calc:
    @traced("a", "b")
    def add(self, *args):
        return sum(args)
```

## `trace_object` envolve o objeto, mas as chamadas ainda não são traçadas

**Causa:** você tem uma referência ao objeto *original*, não envolvido, em algum lugar —
`trace_object` retorna um wrapper novo; o objeto que você passou permanece intocado. Uma chamada
feita nessa referência original, ou em `self` de dentro de um método não traçado, ignora o wrapper
completamente.

**Correção:** garanta que todo chamador tenha o objeto que `trace_object(...)` retornou, não o que
você construiu. Normalmente isso significa envolver uma única vez, em uma raiz de composição ou em
uma fixture, e passar a referência envolvida por todo o fluxo posterior.

## Traces entre threads ou tasks estão vazios, ou um filho bifurcado aparece como uma nova raiz

**Causa:** `ContextVarNarrativeContext` isola threads *e* tasks do asyncio por design — trabalho
submetido a um thread pool ou lançado como uma task só se junta ao trace pai se recebeu um snapshot
de contexto, ou passou por `ForkJoinGroup`/`FireAndForgetGroup`. Um worker que nunca recebeu nenhum
dos dois registra em seu próprio contexto separado. Separadamente: fazer fork diretamente dentro de
um método traçado `async def` resolve o pai através da pilha de chamadas *síncrona*, que está vazia
dentro de uma corrotina, então os filhos lançados dessa forma acabam como irmãos/raízes em vez de
aninhados sob o chamador `async` — uma lacuna conhecida e ainda aberta.

**Correção:** tire um snapshot explícito no limite, ou use `ForkJoinGroup.create(...)` /
`FireAndForgetGroup.create(...)` a partir de um método síncrono (ou de um baseado em thread pool) em
vez de diretamente dentro de `async def`. Se você só precisa do trace próprio do trabalho bifurcado,
chame `capture_trace()` dentro da task, na thread ou task que a registrou.

## A pontuação de clareza parece errada

**Causa:** normalmente é um nome genérico que o analisador sinaliza — `get`, `set`, `process`,
`handle`, `data`, `info`, `temp` e similares pontuam baixo independente do contexto; um nome que sua
equipe aceita como vocabulário de domínio, mas que os dicionários embutidos não conhecem, pontua
como desconhecido, não como específico de domínio.

**Correção:** revise a lista de problemas em `clarity-report.md` e ou renomeie (`getData()` →
`fetchOrderHistory()`), ou ensine seu vocabulário ao analisador através de um `glossary.json`
commitado — veja o [Guia de clareza](guia-de-clareza.md).

## `DuplicateConfigurationError` na inicialização

**Causa:** o mesmo diretório tem tanto um `narrativetrace.toml` quanto um `pyproject.toml` com uma
tabela `[tool.narrativetrace]`. A resolução de configuração se recusa a escolher um silenciosamente.

**Correção:** mantenha exatamente uma fonte de configuração por diretório — apague ou combine uma
das duas. Veja o [Guia de configuração](guia-de-configuracao.md).

## O middleware ASGI não captura uma rota que eu esperava que pulasse, ou pula uma que eu esperava que capturasse

**Causa:** `excluded_paths` compara o caminho da requisição por string exata, não um glob ou prefixo
— excluir `/health` não exclui `/health/live`, e apenas escopos HTTP são capturados (escopos
WebSocket e lifespan sempre passam intocados).

**Correção:** liste explicitamente cada caminho que você quer excluir, ou faça a correspondência
antes, na sua própria camada de roteamento, antes do middleware rodar. Veja o
[Guia de FastAPI/ASGI](guia-de-fastapi-asgi.md).

## Um valor que eu esperava que fosse ocultado aparece em um trace

**Causa:** a lista de negação compara pelo *nome do campo ou parâmetro*, não de forma geral com
"tudo chamado `data`" — um valor armazenado sob um nome que a lista de negação não reconhece (e que
não parece um JWT, número de cartão, string `Set-Cookie` ou número de identidade nacional pela
forma) não é ocultado por padrão. Separadamente: um template de narração `{param.path}` sempre
verifica a lista de negação *padrão*,
mesmo que o `ValueRenderer` ao redor tenha sido construído com uma `RedactionPolicy` personalizada ou
desativada para a renderização normal de parâmetros — uma limitação documentada, não um bug.

**Correção:** marque o membro explicitamente com `@not_traced(...)` / `not_traced_field(...)` — uma
anotação explícita sempre vence, independente da política. Veja
[Privacidade e ocultação](privacidade-e-ocultacao.md) para o contrato completo e verificado.
