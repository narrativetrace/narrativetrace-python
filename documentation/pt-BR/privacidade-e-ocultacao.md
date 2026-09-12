<!-- source: documentation/privacy-and-redaction.md blob cbdc6dc9fc64 | translated: 2026-09-12 | reviewed: - -->

# Privacidade e ocultação

Esta biblioteca roda dentro do seu processo e grava arquivos que sua equipe vai compartilhar —
artefatos de CI, linhas de log de produção. Esta página é a versão linha por linha desse contrato: o
que é ocultado, até onde isso alcança e até onde não alcança, e o que o NarrativeTrace garante versus
o que ele não promete de forma alguma. Verificado diretamente contra
`packages/narrativetrace/src/narrativetrace/redaction.py` e `template.py`, não inferido de outra
documentação.

## Ocultação, superfície por superfície

| Superfície | Dá para desativar a ocultação embutida? |
|---|---|
| Saída do plugin do pytest | Não |
| Middleware ASGI (exportação de metadados de requisição/usuário) | Não |
| Ponte com OpenTelemetry | Não |
| Processador de structlog / ponte de logging da stdlib | Não |
| Um `ValueRenderer` personalizado que seu próprio código constrói | Sim — apenas passando `RedactionPolicy.DISABLED` para `trace_object(obj, context, renderer=ValueRenderer(redaction_policy=RedactionPolicy.DISABLED))` explicitamente |
| `@not_traced` / `not_traced_field(...)` | Não aplicável — é o que faz a ocultação acontecer, e sempre vence |
| Artefato estrutural `.nt` *(since 0.1.2, unreleased)* | Não aplicável — ele não carrega nenhum valor para ocultar, de saída |

Toda integração distribuída renderiza valores através do mesmo mecanismo `ValueRenderer`/
`RedactionPolicy` que o `trace_object` usa por padrão (`RedactionPolicy.DEFAULT`) — nenhuma delas
expõe uma flag de configuração, variável de ambiente ou ajuste de plugin que chegue a `DISABLED`. A
única forma de chegar lá é código de aplicação que constrói seu próprio `ValueRenderer` e o passa
explicitamente — um ato deliberado e revisável no seu próprio código-fonte, não um estado que um
deploy possa alterar silenciosamente.

## O que a lista de negação pega, e o que a supera

Dois mecanismos de ocultação independentes se aplicam a todo valor renderizado por reflexão:

1. **`@not_traced("param")` / `not_traced_field(...)` / `__nt_not_traced__`** — sempre oculta,
   incondicionalmente, independente da política.
2. **A lista de negação baseada em nome** (`RedactionPolicy.DEFAULT`) — uma correspondência de
   substring sem diferenciar maiúsculas de minúsculas nem acentos contra nomes de campo/parâmetro,
   **multilíngue e sempre ativa, sem localidade para selecionar**: o inglês (`password`, `secret`,
   `token`, `cvv`, `ssn`, `apikey`, `cardnumber`, `sessionid`, `passphrase`, `otp`, `bearer`, e
   mais) convive com palavras em espanhol, português, francês, alemão e chinês (`contraseña`,
   `senha`, `motDePasse`, `passwort`, `密码`, e mais) — `pan`/`iban` e oito palavras não inglesas
   correspondem em limites de token do identificador em
   vez de como substrings soltas, especificamente para que `companyName` ou `japaneseAddress` não
   sejam pegos por engano — mais uma segunda verificação independente sobre a *forma* do próprio
   valor: um JWT, uma string `Set-Cookie`, uma sequência de dígitos com forma de número de cartão,
   ou um número de identidade nacional (RUT chileno, CPF/CNPJ brasileiro, DNI/NIE espanhol, NIR
   francês, identidade de residente chinesa, SSN americano) que passa em seu próprio dígito
   verificador ou regra estrutural — um SSN americano não tem dígito verificador, então os
   valores de área/grupo/série nunca emitidos pela SSA fazem esse trabalho em seu lugar — então
   um token bearer ou um número de identidade passado sob um nome não reconhecido ainda assim é
   pego.

Um `NamedTuple` é introspectado pelo nome do campo em vez de renderizado como uma tupla posicional
anônima, então um campo oculto dentro de um permanece oculto da mesma forma que um campo de
dataclass — a ocultação sobrevive um nível de container. E ela vence sobre um template de narração
que o nomeia: `{param.property}` em `@narrated`/`@on_error` resolve um caminho até um membro oculto
como `[REDACTED]`, em toda profundidade do caminho, nunca com o valor literal.

**O próprio `__str__`/`__repr__` de um tipo composto nunca é confiável** *(since 0.1.2,
unreleased)*. Qualquer objeto que carregue estado de instância — uma dataclass, uma classe attrs, um `NamedTuple`, ou um
objeto simples com `__dict__`/`__slots__` preenchido — é introspectado campo a campo independente
de também definir um `__str__`/`__repr__` personalizado; esse método escrito à mão nunca é
consultado para ele. Antes dessa correção, o `ValueRenderer` confiava no `__str__` próprio de uma
classe simples assim que ele sobrescrevia o padrão, então um `__str__` escrito à mão que
interpolasse um campo sensível — diretamente, ou transitivamente através do `__str__` de um objeto
aninhado — chegava à saída completamente sem mediação, passando pela lista de negação, pelos
limites de profundidade, por tudo. Uma chave de dict/map tinha a mesma brecha: costumava ser um
`str(key)` nu e sem mediação, então um objeto sensível usado como chave vazava incondicionalmente,
independente do que seu valor contivesse. Ambos agora são introspectados e verificados contra a
ocultação exatamente como um valor comum — só um valor genuinamente folha (sem nenhum estado de
instância: um número, uma string, uma classe auxiliar sem estado, um membro de `Enum` sem payload)
ainda confia no seu próprio `str()`. `@narrative_summary` não é afetado e continua sendo a forma
suportada de dar a um composto um resumo curado de uma linha em vez do padrão campo a campo.

**Um tipo definido pela plataforma é confiável para seu próprio `str()` mesmo carregando estado**
*(since 0.1.2, unreleased)*. A regra acima é correta para tipos de aplicação, mas era ampla demais
para os próprios tipos de valor da biblioteca padrão — `pathlib.Path`, `datetime`,
`decimal.Decimal`, `uuid.UUID`, `fractions.Fraction` e `ipaddress.*` carregam todos estado de
instância e estavam sendo introspectados campo a campo até virar uma saída ilegível ou inacessível
em vez de sua forma curta normal. A exceção é decidida por **origem, nunca por nome**: um tipo é
confiável só quando seu `__module__` nomeia um pacote de nível superior da biblioteca padrão
(`sys.stdlib_module_names`) ou é um tipo nativo genuíno do interpretador (sem a flag de tipo de
heap) — nunca um prefixo de nome, nem uma lista de permissões mantida manualmente. Quatro casos
fixam a regra: um tipo de plataforma da lista renderiza seu valor curto; um campo ou parâmetro com
nome da lista de negação (`token`, por exemplo) ainda oculta mesmo quando seu valor é um tipo de
plataforma, porque o eixo do nome é verificado primeiro e nunca chega à exceção; uma classe de
usuário que só compartilha o nome de um tipo de plataforma (um "impostor") é introspectada, não é
confiável, porque o teste nunca examina o nome próprio de uma classe; e uma **subclasse** de
usuário de um tipo de plataforma também é introspectada, porque o `__module__` próprio de uma
subclasse é onde *ela* foi definida, nunca herdado de sua base de plataforma. O mesmo raciocínio,
aplicado ao eixo de identidade de classe, das verificações de lista de negação e de forma acima: um
tipo de plataforma não pode carregar um campo de aplicação da lista de negação, então confiar no
seu texto é ao mesmo tempo a resposta legível e a segura.

Quando um método `@narrative_summary`, um `__str__` personalizado, ou o próprio getter de um campo
lança uma exceção *(since 0.1.2, unreleased)*, essa parte é renderizada como `<error: <TypeName>>` — o nome do TIPO da exceção
(`<error: ValueError>`, `<error: RecursionError>`) substituído só para aquela parte. A *mensagem* da
exceção deliberadamente nunca é renderizada, porque uma mensagem pode carregar o próprio valor que
falhou ao renderizar; só o nome do tipo chega à saída, nunca `str(exc)`.

**Uma limitação documentada, registrada em vez de corrigida.** A resolução de marcadores de template
(`{param}`, `{param.property}`) sempre verifica os valores contra `RedactionPolicy.DEFAULT` — a
política não é propagada a partir de um `ValueRenderer` personalizado que você passa para
`trace_object`. Na prática isso só importa se você também construir uma política personalizada ou
desativada: a renderização normal de parâmetros e valores de retorno respeita essa política
personalizada, mas um template `@narrated`/`@on_error` que resolve o mesmo valor ainda verifica por
baixo a lista de negação padrão. `@not_traced` não é afetado — sempre oculta independente de qual
política esteja em vigor.

Detalhe completo e exemplos trabalhados: [Guia de decoradores](guia-de-decoradores.md).

## Garantias

- **Falhas de tracing são isoladas da execução do host.** O registro é isolado de exceções em todo
  caminho; um `__str__` que lança exceção, um buffer cheio ou um handler de log quebrado nunca mudam
  o que seu método retorna ou lança.
- **A saída não pode ser forjada.** Valores renderizados, mensagens de exceção e texto de narração
  passam por um escape de caracteres de controle e substitutos (surrogates) antes de chegar a uma
  linha de log, um renderizador de console ou um documento Markdown — então um valor não consegue
  injetar uma linha de log falsa nem quebrar a formatação do artefato.
- **O caminho de análise em buffer pode descartar eventos, mas sempre relata a perda.** É um anel de
  tamanho fixo (65.536 slots por padrão — o parâmetro do construtor `buffer_capacity` do
  `BufferedEventConsumer`, para código que constrói seu próprio pipeline) que sobrescreve o evento
  mais antigo sob carga sustentada em vez de crescer sem limite ou bloquear quem chamou; uma execução
  que perdeu eventos imprime a contagem na sua própria linha de rodapé `Incomplete:` da suíte em vez
  de subrrelatar silenciosamente.
- **A introspecção lê dados armazenados, não código.** Nomes de campo vêm de
  `dataclasses.fields()`, metadados do attrs, o `_fields` de um `NamedTuple`, ou o
  `__dict__`/`__slots__` da instância — um getter de `@property` calculado nunca é enumerado nem
  executado durante a introspecção.
- **O artefato estrutural `.nt` não carrega nenhum valor de tempo de execução** *(since 0.1.2,
  unreleased)*. Apenas nomes, hierarquia de chamadas e tipos de desfecho — zero superfície de
  injeção de prompt, fixado por um teste de conformidade byte a byte contra o formato de
  referência, não uma política que alguém poderia esquecer de aplicar. Seu cabeçalho `scenario:` é
  coberto por essa mesma garantia: uma invocação de um caso `@pytest.mark.parametrize` é intitulada
  `<method> #<index>`, nunca o nome de exibição no qual um id de parametrize interpolou seus
  argumentos. O que o artefato é *chamado* — seu nome de arquivo — é uma questão diferente; veja a
  não garantia abaixo.

## Não garantias

- **Nenhuma promessa de "custo zero".** O tracing faz trabalho, e trabalho custa algo — veja a
  [seção de desempenho do LEIAME](../../LEIAME.md#desempenho).
- **Nenhum tracing de métodos privados.** `trace_object` só intercepta acesso a atributos públicos
  (`__getattr__`); um nome começando com `_` nunca é envolvido, e métodos dunder (`__str__`,
  `__eq__`, …) são resolvidos no tipo e também nunca chegam ao wrapper — então
  `str()`/`repr()`/`==`/`isinstance()` de um objeto envolvido param de refletir o objeto original
  silenciosamente, sem marcador ou API de desembrulho para detectar o wrap de fora.
- **Nenhum tracing automático de um objeto que você não envolveu explicitamente.** Não há import
  hook, nem instrumentação de bytecode, nem auto-wrap em nível de framework disponível hoje — veja
  [Escolhendo uma integração](escolhendo-uma-integracao.md).
- **A ocultação é baseada em nome e forma, não em uma análise de fluxo de dados.** Um valor sensível
  armazenado sob um nome que a lista de negação não reconhece, e que não corresponde a nenhuma forma
  de segredo conhecida, não é ocultado a menos que você o marque explicitamente.
- **Nenhum nome de teste é ocultado.** O nome de exibição de um teste — incluindo um id de
  `@pytest.mark.parametrize` (`test_finds_it[KAYAK]`) — é texto identificador escrito pelo
  desenvolvedor ou gerado pelo runner, não um valor capturado: ele chega literalmente
  (humanizado, nunca ocultado) ao artefato que carrega valores, no seu cabeçalho
  `scenario:`/`**Scenario:**` Markdown/JSON e no seu nome de arquivo, e o `manifest.json` nomeia o
  cenário da mesma forma. Nenhuma lista de negação é consultada para ele, e isso é proposital
  (contrato multiplataforma do cabeçalho estrutural) — o único lugar onde isso *é* resolvido para
  você é o artefato `.nt` livre de valores *(since 0.1.2, unreleased)*: o cabeçalho estrutural de
  uma invocação é intitulado pelo método e seu índice de invocação, nunca pelo nome de exibição no
  qual um id de parametrize interpolou argumentos (veja a garantia acima e o
  [Formato de trace estrutural](formato-de-trace-estrutural.md)). Mantenha segredos fora dos ids de
  `parametrize` do mesmo jeito que você os manteria fora de um template `@narrated`/`@on_error` — o
  artefato que carrega valores, seu nome de arquivo, e o `manifest.json` ainda os carregam
  literalmente.

## O modelo de perda em produção, visualmente

As duas metades do pipeline de caminho duplo (registro de decisão de produto PY-002) carregam
obrigações opostas por design:

```text
caminho de log síncrono (logging da stdlib, inline na thread de quem chamou)
   não pode falhar a aplicação host
   durável — este é o registro

caminho de análise em buffer (anel limitado, drenado por uma thread em segundo plano)
   pode descartar eventos sob carga, e sempre diz isso
   nunca pode bloquear quem chamou
   nunca pode crescer além do seu limite (65.536 slots por padrão)
   melhor esforço — isto é análise, não auditoria
```

Perder o buffer perde fidelidade de análise — árvores de trace capturadas, pontuação de clareza,
spans do OTel — para os eventos descartados durante aquela janela. Perder o fluxo de log perde o
registro. Essa assimetria é a razão de serem dois caminhos com dois comportamentos de falha
diferentes, em vez de um único caminho com uma única contrapartida.

## O que esta página não cobre

O que acontece quando o NarrativeTrace se empilha com proxies estilo AOP, bibliotecas de contrato, ou
outra ferramenta envolvendo os mesmos objetos segue dois invariantes — um único frame de trace por
cruzamento de fronteira de negócio, e nenhum resultado que dependa da ordem dos wrappers — cobertos
na [seção de privacidade e segurança do LEIAME](../../LEIAME.md#privacidade-e-segurança). Todo nível
de tracing e toda opção de formato de saída, incluindo como `NARRATIVETRACE_LEVEL` controla a
captura antes de qualquer renderização acontecer, está no [Guia de configuração](guia-de-configuracao.md).
