<!-- source: README.md blob 213a680ed90f | translated: 2026-09-12 | reviewed: - -->

# NarrativeTrace (Python)

[English](README.md) | [Español](LEAME.md) | **Português** | [简体中文](自述文件.md)

## Comece aqui

[Veja um trace em 60 segundos](documentation/pt-BR/sessenta-segundos.md) — um script simples, uma execução, e o trace aparece no seu terminal.

## Demo

Clone o repositório e rode `./demo.sh`.

## Exemplos

Veja [os exemplos](examples/README.md) — o NarrativeTrace em aplicações reais.

## O código é o log

O NarrativeTrace transforma código Python em execução em uma narrativa legível, construída a partir
dos nomes de método, classe e parâmetro que você já escreveu. Sem linhas `logger.info(...)`. Se o
trace é ilegível, seu código precisa de nomes melhores — não de mais declarações de log.

## O problema

Metade deste método é ruído de logging:

```python
def place_order(self, customer_id, product_id, quantity):
    logger.info("Placing order for customer %s product %s qty %s", customer_id, product_id, quantity)
    inventory = self.inventory.reserve(product_id, quantity)
    logger.debug("Reserved inventory: %s", inventory)
    payment = self.payments.charge(customer_id, inventory.total)
    logger.info("Payment processed: %s", payment.transaction_id)
    return OrderResult(payment.transaction_id, inventory.items)
```

A lógica de negócio são três linhas; o logging são quatro. Cada desenvolvedor escreve esses logs de
forma diferente — mensagens diferentes, níveis diferentes, valores diferentes incluídos. O resultado
é inconsistente, verboso e emaranhado com o código que descreve.

O NarrativeTrace elimina isso por completo:

```python
def place_order(self, customer_id, product_id, quantity):
    inventory = self.inventory.reserve(product_id, quantity)
    payment = self.payments.charge(customer_id, inventory.total)
    return OrderResult(payment.transaction_id, inventory.items)
```

Lógica de negócio pura. O trace é gerado a partir dos nomes de método, nomes de parâmetro e valores
de retorno — a informação que já estava ali.

## Como fica a saída

Envolva os colaboradores uma vez e rode o código; esta é a saída real de um fluxo de pedido com três
serviços (`OrderService` chamando um `InventoryService` e um `PaymentService`, ambos também
envolvidos):

```
OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
├── InventoryService.reserve(product_id: "prod-42", quantity: 3) → "reserved 3 of prod-42" — 0ms
├── PaymentService.charge(customer_id: "cust-1", amount: 30) → "txn-cust-1-30" — 0ms
└── → "order placed: txn-cust-1-30" — 0ms
```

**Quando algo dá errado**, o trace torna o bug visível:

```
OrderService.place_order(customer_id: "cust-broke", product_id: "prod-7", quantity: 3)
├── InventoryService.reserve(product_id: "prod-7", quantity: 3) → "reserved 3 of prod-7" — 0ms
├── PaymentService.charge(customer_id: "cust-broke", amount: 30) !! PaymentDeclinedError: payment declined for customer cust-broke — 0ms
└── !! PaymentDeclinedError: payment declined for customer cust-broke — 1ms
```

`InventoryService.reserve` foi chamado mas `InventoryService.release` não aparece em lugar nenhum do
trace — o bug é visível sem um depurador.

**O trace é tão bom quanto os seus nomes.** O mesmo fluxo "player entra no mundo" de
[`examples/minecraft`](examples/minecraft), traçado duas vezes — uma com nomes de domínio, outra com
nomes genéricos, ambas as execuções reais:

```
→ WorldServer.player_joined(player_name: "Steve")
  → WorldGenerator.generate_chunk(x: 0, z: 0)
  ← WorldGenerator.generate_chunk → Chunk(x=0, z=0, biome="plains")
  → PlayerInventory.add_item(item: Item.OAK_LOG, quantity: 4)
  ← PlayerInventory.add_item → True
  → CraftingTable.craft(recipe: Recipe.WOODEN_PICKAXE)
  ← CraftingTable.craft → Item.WOODEN_PICKAXE
  → CreatureSpawner.spawn_hostile(type: CreatureType.ZOMBIE, x: 10, y: 64, z: 20)
  ← CreatureSpawner.spawn_hostile → Creature(type=CreatureType.ZOMBIE, x=10, y=64, z=20)
← WorldServer.player_joined → "Steve joined the world"
```

```
→ GameManager.handle(input: "Steve")
  → DataProcessor.process(a: 0, b: 0)
  ← DataProcessor.process → DataResult(a=0, b=0, tag="plains")
  → StateManager.update(type: 1, count: 4)
  ← StateManager.update → True
  → ThingFactory.create(type: 1)
  ← ThingFactory.create → 1
  → EntityHandler.execute(kind: 1, a: 10, b: 64, c: 20)
  ← EntityHandler.execute → Entity(kind=1, a=10, b=64, c=20)
← GameManager.handle → "Steve joined the world"
```

Mesmo grafo de chamadas, mesmos valores de retorno, só os nomes mudam — `narrativetrace-clarity` põe
um número na diferença (0.72 contra 0.53 nas duas execuções acima). Se o seu código não consegue
contar sua própria história, ele precisa de refatoração, e é por isso que o NarrativeTrace também
[pontua seus nomes](documentation/pt-BR/guia-de-clareza.md).

### Por que isso importa para o desenvolvimento assistido por IA

Toda linha `logger.info(...)` é uma linha que as ferramentas de IA para código precisam parsear,
gastar tokens e contornar ao raciocinar. Remova-as e o mesmo orçamento de tokens cobre mais do seu
código real, o modelo vê o que o código faz em vez de como ele registra em log, e os pull requests
mostram mudanças de lógica de negócio em vez de mudanças misturadas de lógica e logging.

### Como se compara

Diferente de uma árvore de spans do OpenTelemetry (construída para máquinas e dashboards), um
NarrativeTrace se lê como prosa para humanos e LLMs. Os dois se combinam: `narrativetrace-otel` emite
o mesmo trace como spans tipados do OTel, então você ganha a narrativa humana *e* a correlação de
backend a partir de uma única captura.

### Não substitui sua stack de logging

O NarrativeTrace não é um framework de logging. Ele não traz handler, nem formatter, nem
pipeline de envio — sua configuração de `logging` (handlers, formatters,
`dictConfig`/`fileConfig`) ou sua cadeia de processadores do structlog continua rodando
exatamente como hoje.

O que ele substitui são as sentenças de narração escritas à mão — as linhas
`logger.info("Placing order %s for customer %s", ...)` de [o problema](#o-problema) acima. Um
método rastreado produz essa mesma narrativa automaticamente, a partir dos valores reais de
parâmetros e retorno na chamada, sem nenhum código de narração no corpo do método. Essa
narrativa é capturada pelo seu próprio caminho — sem interceptar ou reconfigurar seu pipeline de
logging.

Duas pontes opcionais permitem que essa narrativa — ou só sua identidade — viaje pela sua stack
existente, sem modificá-la:

- **`LoggingTraceConsumer`** envia as linhas geradas de entrada/retorno/exceção através de
  `logging.getLogger("narrativetrace").log(...)` — a mesma chamada que uma sentença escrita à
  mão faria, então cada handler e formatter que você já tem continua recebendo-as, intactos.
- **`narrativetrace-structlog`** não gera linhas de jeito nenhum: seu processador carimba as
  mesmas chaves de correlação (`traceId`, `spanId`, `nt.class`, `nt.method`, …) em cada
  dicionário de evento que já flui pela sua cadeia de processadores, incluindo as que você
  escreveu à mão. O `NarrativeContextFilter` faz o equivalente para o `logging` padrão, como um
  `Filter` no seu próprio handler.

Uma sentença `logger.info(...)` escrita à mão ao lado de uma chamada rastreada se mistura
livremente — mesmo logger, mesmo stream, mesmos handlers. O NarrativeTrace só adiciona ao que já
existe.

## Adicione a um teste

O caminho mais curto de "biblioteca interessante" a "vi um trace útil do meu próprio código" é o
plugin do pytest. Python ≥ 3.12.

**1. Instale-o** — traz o core, os renderizadores de diagrama e o motor de clareza:

```bash
uv add --dev narrativetrace-pytest
```

**2. Traçe um serviço em um teste** — o plugin se registra sozinho; basta pedir a fixture:

```python
from narrativetrace import trace_object

class TestOrderService:
    def test_customer_places_order(self, narrative_trace):
        service = trace_object(OrderService(), narrative_trace)
        service.place_order("C-1234", "SKU-KB", 2)
```

**3. Rode a suíte — os artefatos são gravados por padrão** *(since 0.1.2, unreleased)* — a versão
publicada no PyPI, `0.1.1`, ainda vem com isso desligado; ative `NARRATIVETRACE_OUTPUT=true`
explicitamente nessa versão:

```bash
uv run pytest
```

**4. Abra a narrativa** — a classe de teste virou o diretório, o método de teste virou o arquivo:

```text
narrative-traces/traces/TestOrderService/test_customer_places_order.md
```

Esta é a saída real, de uma execução de verdade, desse exato teste:

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

Cada teste grava seu próprio conjunto de artefatos — `.json` complementar e
`diagrams/<Class>/<slug>.mmd` para o formato `markdown` padrão, mais um `clarity-report.md` para
toda a suíte:

```text
narrative-traces/
├── traces/<TestClass>/<slug>.md         a narrativa humana
├── traces/<TestClass>/<slug>.json       o mesmo trace como JSON canônico
├── diagrams/<TestClass>/<slug>.mmd      diagrama de sequência Mermaid
├── clarity-results.json                 pontuações de nomes, uma entrada por teste
└── clarity-report.md                    feedback de nomes para toda a suíte
```

Coloque `narrative-traces/` no seu `.gitignore` — ele é regenerado a cada execução (veja
[o-que-commitar.md](documentation/pt-BR/o-que-commitar.md)). Não quer isso? Defina
`NARRATIVETRACE_OUTPUT=false`.

Quer continuar — renomear o método e ver a pontuação de clareza cair, ou adicionar `@not_traced` e
ver um valor ocultado? O [Guia de clareza](documentation/pt-BR/guia-de-clareza.md) e
[Privacidade e ocultação](documentation/pt-BR/privacidade-e-ocultacao.md) percorrem os dois com
saída real.

## Escolha sua integração

Testes são onde a maioria começa. Aqui está para onde ir a seguir:

| Você quer | Comece com |
|---|---|
| Traces em testes, com o mínimo de cabeamento | `narrativetrace-pytest` (fixture `narrative_trace`) |
| Controle explícito sobre o que é envolvido, em Python puro | `trace_object(obj, context)` — o core, sem necessidade de framework |
| Ciclo de vida de requisições do FastAPI/Starlette | `narrativetrace-asgi` |
| Propagar um trace para uma chamada HTTP downstream | `attach_traceparent` do `narrativetrace-asgi` (httpx) |
| Traces no seu fluxo de log de produção | `LoggingTraceConsumer` / `NarrativeContextFilter` (core) |
| Pipelines de structlog | `narrativetrace-structlog` |
| Spans do OpenTelemetry | `narrativetrace-otel` |
| Diagramas de sequência | `narrativetrace-diagrams` |
| Gate de CI para qualidade de nomes | script de console `narrativetrace-clarity` |
| Flask (WSGI) ou Django | Ainda não lançado — veja [Escolhendo uma integração](documentation/pt-BR/escolhendo-uma-integracao.md) |

Não existe aqui um mecanismo de anexação em nível de bytecode e sem código — todo caminho acima é
uma chamada explícita a `trace_object(...)` ou um middleware que você mesmo registra; nada reescreve
suas classes ao carregá-las. Detalhe completo, um diagrama de decisão, e o que acontece quando o
NarrativeTrace se empilha com outros wrappers: [Escolhendo uma
integração](documentation/pt-BR/escolhendo-uma-integracao.md).

### Pacotes

| Pacote | Propósito |
|---|---|
| [`narrativetrace`](packages/narrativetrace) | Core sem dependências: captura, decoradores, renderização, ocultação, concorrência, exportação JSON, ponte de logging |
| [`narrativetrace-pytest`](packages/narrativetrace-pytest) | Plugin do pytest: fixture `narrative_trace` por teste, artefatos, rodapé de clareza |
| [`narrativetrace-diagrams`](packages/narrativetrace-diagrams) | Renderizadores de diagrama de sequência Mermaid + PlantUML |
| [`narrativetrace-otel`](packages/narrativetrace-otel) | Ponte de spans do OpenTelemetry (listener ao vivo + exportador em lote) |
| [`narrativetrace-asgi`](packages/narrativetrace-asgi) | Middleware ASGI (Starlette/FastAPI), traceparent W3C, acessor de requisição |
| [`narrativetrace-clarity`](packages/narrativetrace-clarity) | Motor de clareza de nomes + script de console de gate de CI |
| [`narrativetrace-structlog`](packages/narrativetrace-structlog) | Processador de structlog que injeta chaves de correlação |
| [`narrativetrace-glossary`](packages/narrativetrace-glossary) | Glossário de domínio: o modelo `glossary.json`, leitor/escritor determinístico, visão em Markdown |

## Privacidade e segurança

Esta biblioteca roda dentro do seu processo e grava arquivos que sua equipe vai compartilhar. O que
isso significa, em uma tela:

| Superfície | Dá para desativar a ocultação embutida? |
|---|---|
| Plugin do pytest, middleware ASGI, ponte OTel, processador de structlog, ponte de logging da stdlib | Não |
| Um `ValueRenderer` personalizado que seu próprio código constrói | Sim — apenas passando `RedactionPolicy.DISABLED` explicitamente |
| `@not_traced` / `not_traced_field(...)` | Não aplicável — é o que faz a ocultação, e sempre vence |

`@not_traced` em um parâmetro ou campo, e a lista de negação baseada em nome (`password`, `token`,
`cvv`, `ssn`, …) mais o mascaramento por forma de valor (strings com forma de JWT/PAN/`Set-Cookie`,
independente do nome do campo), se aplicam em todo lugar onde um valor é renderizado por reflexão —
nenhuma integração distribuída expõe uma forma de contorná-los. Uma limitação conhecida e
documentada: um template de narração `{param.path}` sempre verifica a lista de negação padrão, mesmo
quando o renderizador ao redor foi construído com uma política personalizada ou desativada — veja
[Privacidade e ocultação](documentation/pt-BR/privacidade-e-ocultacao.md) para o escopo exato.

- **Falhas de tracing não podem falhar sua aplicação.** O registro é isolado de exceções em todo
  caminho; um `__str__` que lança exceção ou um buffer cheio nunca mudam o que seu método retorna
  ou lança.
- **O uso de recursos é limitado.** O caminho de análise em buffer é um anel de tamanho fixo (65.536
  eventos por padrão) que descarta em vez de bloquear sob carga — e diz isso: uma execução que
  perdeu eventos imprime a contagem no seu próprio rodapé de suíte em vez de subrrelatar
  silenciosamente.
- **A introspecção lê dados armazenados, não código.** Um getter de `@property` calculado nunca
  executa; os únicos membros que o NarrativeTrace invoca são um método `@narrative_summary`
  cuidadosamente escrito, um `__str__` personalizado quando o tipo não carrega nenhum campo, e
  caminhos de propriedade nomeados em um template `@narrated`/`@on_error` — mantenha-os puros,
  como você faria para um depurador. O próprio `__str__` de um composto, do contrário, nunca é
  confiável *(since 0.1.2, unreleased)*: qualquer objeto que carregue estado de instância é introspectado campo
  a campo independente de definir um `__str__` personalizado, então um escrito à mão não consegue
  driblar a ocultação, nem diretamente nem através de um objeto aninhado — uma chave de dict/map
  passa pela mesma verificação. Um resumo/`__str__`/getter que lança exceção renderiza
  `<error: TypeName>` para aquela parte, nunca a própria mensagem da exceção.

→ [Privacidade e ocultação](documentation/pt-BR/privacidade-e-ocultacao.md) para o contrato linha por
linha verificado contra o código.

**Coexistindo com outros wrappers.** Bibliotecas de contrato, proxies DI/AOP, e agentes de
observabilidade (incluindo a auto-instrumentação do OpenTelemetry) podem envolver o mesmo método que
o NarrativeTrace envolve. Esta implementação mantém duas regras para seus próprios mecanismos: um frame de
trace por cruzamento de fronteira de negócio — métodos ponte e maquinário gerado por container nunca
são narrados — e nenhum resultado depende de qual wrapper está mais externo, então o resultado ou a
exceção de uma chamada envolvida sempre chega ao trace independente da ordem de empilhamento. O
`excluded_paths` do `narrativetrace-asgi` é a única opção de exclusão disponível hoje (com escopo de
caminho, correspondência exata); `trace_object` não tem nada para excluir por padrão, já que envolve
uma única instância que você entrega a ele, não uma varredura.

## Desempenho

A captura é controlada por um nível de tracing verificado *antes* de qualquer renderização acontecer
(`NARRATIVETRACE_LEVEL`): defina-o como `OFF` e os wrappers fazem short-circuit — sem reflexão, sem
trabalho de strings — antes de tocar nos seus argumentos. Para loops quentes, restrinja o escopo
traçado ou baixe o nível em vez de traçar tudo.

Existe uma suíte de benchmarks inicial (`packages/narrativetrace/tests/test_bench_*.py`, executada
com `uv run poe bench`): overhead de captura por nível de tracing, uma chamada através de
`trace_object` contra uma chamada direta, a renderização de uma trace capturada em cada formato, e
a verificação de redação em um caminho quente. Ainda não publicamos números oficiais a partir dela
da forma que o irmão Java publica suas cifras de JMH — `uv run poe bench-gate` compara uma execução
com a anterior na *mesma* máquina (números de referência de uma máquina não são comparáveis entre
máquinas), por isso isso é um hábito noturno, não um número público. Não assuma que os números do
Java se transferem: os runtimes, e o que cada linha de código de tracing custa neles, são
diferentes. Não vamos afirmar "overhead zero" de nenhuma forma — o tracing faz trabalho, e
trabalho custa algo.

## O que é gratuito e o que é Pro

**Gratuito** é tudo neste repositório — de código disponível sob BSL 1.1, gratuito em produção,
convertendo para Apache 2.0 quatro anos após cada versão: todo o runtime, traces por teste em todos
os formatos, pontuação de clareza, o glossário de domínio, e toda integração na tabela acima.

**Pro** é inteligência *entre* execuções, construída sobre a mesma captura: hoje isso é agregação de
stream de eventos (`EventAggregator` — árvores agregadas, hotspots, taxas de erro), distribuída em uma
distribuição comercial separada, nunca neste repositório. Resumos de fluxo, diffs de
migração, grafos de dependência em tempo de execução, e handlers de ferramentas MCP para agentes de
IA estão planejados lá a seguir. O [Guia de funcionalidades](documentation/pt-BR/guia-de-funcionalidades.md)
é a tabela de status autoritativa: ela rotula cada funcionalidade como Gratuito, Pro, Em
desenvolvimento, ou Planejado, e cita o código por trás de cada linha lançada.

## Concorrência

Grupos fork-join e fire-and-forget propagam a identidade completa do trace através de tasks do
`asyncio` e thread pools, então o trabalho concorrente é enxertado de volta sob o span que o lançou
com um id de grupo compartilhado — a história permanece coerente mesmo quando a execução não é
sequencial. Um snapshot de contexto leva o trace *para dentro* de um worker e o trabalho traçado ali
*volta*: a pilha que captura reporta a partir do momento em que é publicado, transitivamente através
de uma cadeia de saltos async.

## Desenvolvimento

```bash
uv sync --all-packages
uv run poe check          # format-check + lint + typecheck + lint-imports + coverage + stress-quick + metrics + clarity + no-license-headers + translation-check + legal-check + bandit
```

## Documentação

Comece aqui:

- [Veja um trace em 60 segundos](documentation/pt-BR/sessenta-segundos.md) — um script simples, uma execução, um trace real no seu terminal
- [Escolhendo uma integração](documentation/pt-BR/escolhendo-uma-integracao.md) — qual pacote você precisa, como diagrama de decisão
- [Guia de instalação](documentation/pt-BR/guia-de-instalacao.md) — cada pacote, o que ele adiciona
- [Guia de configuração](documentation/pt-BR/guia-de-configuracao.md) — níveis de tracing, configurações de saída, cadeia de precedência
- [Guia de decoradores](documentation/pt-BR/guia-de-decoradores.md) — `@narrated`, `@on_error`, `@not_traced`, o contrato de pureza

Aprofundando:

- [Privacidade e ocultação](documentation/pt-BR/privacidade-e-ocultacao.md) — o contrato de ocultação linha por linha, verificado contra o código
- [O que commitar](documentation/pt-BR/o-que-commitar.md) — quais arquivos gerados são artefatos de CI, e quais (se algum) são baselines revisadas
- [Solução de problemas](documentation/pt-BR/solucao-de-problemas.md) — sintoma → causa → correção para os modos de falha que as pessoas realmente encontram
- [Guia de pytest](documentation/pt-BR/guia-de-pytest.md) · [Guia de FastAPI/ASGI](documentation/pt-BR/guia-de-fastapi-asgi.md) · [Guia de OpenTelemetry](documentation/pt-BR/guia-de-opentelemetry.md) · [Guia de logging](documentation/pt-BR/guia-de-logging.md) · [Guia de clareza](documentation/pt-BR/guia-de-clareza.md)
- [Guia de funcionalidades](documentation/pt-BR/guia-de-funcionalidades.md) — cada funcionalidade que esta implementação distribui, com nível e status
- [Referência completa (`llms-full.md`)](documentation/llms-full.md) — todos os guias, em um arquivo; [`llms.txt`](documentation/llms.txt) é o índice legível por máquina para agentes de IA

## Perguntas frequentes

### Quanto overhead isso adiciona, e o que acontece sob alta concorrência?

Não vamos afirmar "overhead zero" — e, diferente de outras implementações desta família, ainda não temos números datados e publicados para citar aqui. Existe uma suíte de benchmarks inicial (`packages/narrativetrace/tests/test_bench_*.py`, executada com `uv run poe bench`) cobrindo o overhead de captura por nível de tracing, uma chamada através de `trace_object` contra uma chamada direta, a renderização para cada formato, e a checagem de ocultação em um caminho quente — mas `uv run poe bench-gate` só compara uma execução contra a anterior na *mesma* máquina (números de baseline do host não são comparáveis entre máquinas), então isso é um hábito de regressão noturno, ainda não um número público. Não assuma que os números de Java ou TypeScript se transferem para esta implementação: o que uma linha de código de tracing custa é diferente por implementação. Rode `uv run poe bench` você mesmo no seu próprio hardware se precisar de um número hoje — preferimos não dizer nada aqui do que dizer algo que não podemos sustentar.

O que podemos afirmar com confiança é o mecanismo. A captura é controlada por um nível de tracing checado *antes* de qualquer renderização acontecer: coloque `NARRATIVETRACE_LEVEL=OFF` e `enter_method` retorna `None` imediatamente — sem reflexão, sem trabalho de strings, antes mesmo de tocar seus argumentos. Para loops quentes, restrinja o escopo traçado ou baixe o nível em vez de traçar tudo.

Sob concorrência, os dois caminhos do `DualPathPipeline` padrão têm garantias diferentes. Um listener síncrono — `LoggingTraceConsumer`, a ponte para o `logging` da biblioteca padrão (o análogo nesta implementação do `Slf4jTraceEventListener` do Java) — roda em linha se você conectar um, então é exatamente tão durável — e custa exatamente o mesmo — quanto uma chamada de log já custa. O caminho com buffer, de melhor esforço, é um anel de tamanho fixo (65.536 eventos, nunca cresce) que descarta sob carga em vez de bloquear quem chama, e cada perda é **contada**, nunca em silêncio — `dropped_count()` soma a contrapressão de assinantes, as sobrescritas do buffer e o descarte sob carga juntos, e uma execução que perdeu eventos imprime a contagem na própria linha `Incomplete:` no rodapé da suíte.

**O limite honesto:** hoje não existe sampling nesta implementação, nem em nenhuma implementação do NarrativeTrace — toda chamada traçada é capturada por completo no nível configurado. Um amostrador por porcentagem ou por taxa está no roadmap, mas não foi lançado. Se você precisa limitar o volume de captura agora, use `NARRATIVETRACE_LEVEL=OFF` ou restrinja o escopo traçado ao limite que importa.

### Como sei que um parâmetro com PII ou credenciais não vai vazar em um trace?

Quatro camadas independentes, não uma única promessa geral — o contrato linha a linha, verificado contra o código, é [Privacidade e ocultação](documentation/pt-BR/privacidade-e-ocultacao.md):

1. **`@not_traced("password", "cvv")` em parâmetros nomeados**, e **`not_traced_field(...)`/`__nt_not_traced__` nos campos de uma classe** — ocultação explícita que você controla.
2. **Uma lista de negação por nome, sempre ativa e multilíngue** — compara nomes de campos e parâmetros com padrões em inglês, espanhol, português, francês, alemão e chinês para senhas, tokens, identificações nacionais e afins, sem locale para escolher e nada para ativar.
3. **Correspondência pela forma do valor, independente do nome do campo** — uma string com forma de JWT, um número de cartão válido por Luhn, um valor com forma de `Set-Cookie`, ou um checksum ou regra estrutural de identificação nacional (RUT chileno, CPF/CNPJ brasileiro, DNI/NIE espanhol, NIR francês, carteira de identidade chinesa, SSN americano) é ocultado mesmo que chegue sob um nome inocente como `data` ou `value` — combinado em `is_secret_shaped`.
4. **Ainda não há um modo estrutural sem valores nesta implementação.** O formato `.nt`/`.approved.nt` do irmão Java — a garantia categórica para um contexto onde nenhum valor pode sair do processo — está planejado aqui, não lançado (veja o [Guia de funcionalidades](documentation/pt-BR/guia-de-funcionalidades.md)). Não confunda com `TraceTranslationView`: essa é uma funcionalidade real e lançada, mas ela reglosa os *nomes* dos identificadores para outro idioma via um glossário — os valores continuam passando byte a byte idênticos, intocados, então não é um modo sem valores.

Também não há um conjunto de regras de ocultação configurável por caminho — nada de uma política estilo JSONPath "sempre oculte `user.creditCard`". A ocultação é por nome e por forma, e é aplicada em cada segmento quando um template de narração `{param.property}` resolve um caminho, não é uma análise de fluxo de dados. Seja preciso sobre o limite: as camadas 1–3 são heurísticas e extensíveis — sempre podem deixar passar uma forma ou um nome que ninguém pensou em adicionar ainda. Nenhuma delas é *categórica* como seria o modo estrutural (ainda não lançado). Se o seu modelo de ameaça exigir "nenhum valor pode jamais sair do processo", essa garantia não existe hoje nesta implementação.

### Os IDs de trace podem se correlacionar com um ID de correlação padrão entre serviços, ou o tracing é só local?

Sim — através do W3C `traceparent`, o mesmo mecanismo que o OpenTelemetry usa, e as duas direções estão lançadas. **Entrada:** o middleware ASGI (`NarrativeTraceMiddleware`, `adopt_traceparent=True` por padrão) analisa um cabeçalho `traceparent` de entrada e chama `context.adopt_trace_id(...)` — o próprio `trace_id` do NarrativeTrace **se torna** diretamente o ID de trace desse cabeçalho, não é um identificador separado apenas com uma forma parecida. **Saída:** `attach_traceparent`/`attach_traceparent_async` são hooks de evento do `httpx` que estampam o ID de trace do contexto atual em cada requisição de saída (`packages/narrativetrace-asgi`) — um mecanismo de saída para o qual a implementação Java não tem equivalente. Quando não há cabeçalho presente, um novo ID é gerado na mesma forma W3C de 32 caracteres hexadecimais minúsculos (`TraceId` é tipado exatamente nesse formato). O pacote `narrativetrace-otel` também exporta os spans do NarrativeTrace (`OtelTraceEventListener`, ao vivo; `TraceSpanExporter`, em lote) com atributos tipados `narrative.*` e remoção de órfãos, então seu collector OTel, Jaeger ou middleware de ID de correlação já existentes entendem o ID sem nada para reconciliar.

O que fica local: a árvore narrativa em si — as chamadas de método aninhadas, os argumentos, a narração — é capturada por processo e nunca é enviada a outro serviço; só o ID de trace cruza a fronteira. Um serviço downstream produz sua própria árvore narrativa correlacionada com esse mesmo ID, não uma única árvore combinada entre serviços. (Ainda não há um exemplo multisserviço elaborado em `examples/` que exercite isso de ponta a ponta — o mecanismo é testado no nível de unidade, em `packages/narrativetrace-asgi/tests/test_outbound.py` e nos próprios testes do middleware, não demonstrado como um cenário distribuído em execução.)

## Licença

A API e o formato de saída do NarrativeTrace são padrões abertos (Apache 2.0). Seu runtime é gratuito
e de código disponível (BSL 1.1, convertendo para Apache 2.0 quatro anos após cada versão). Pro é
comercial.

As distribuições deste repositório são esse runtime: **Business Source License 1.1** (SPDX
`BUSL-1.1`) — o texto completo está em [`LICENSE`](LICENSE). O uso em produção é concedido para
qualquer propósito, incluindo uso interno e serviços que você oferece aos seus próprios clientes; a
única exclusão é oferecer o próprio NarrativeTrace — ou um produto ou serviço cujo valor derive
substancialmente dele — a terceiros como um produto ou serviço de logging, tracing ou narrativa de
código. Quatro anos depois que uma versão é publicada, essa versão converte para a Apache License
2.0.

A prosa da documentação é CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/); os arquivos de
esquema JSON são Apache 2.0.

Nenhuma dessas licenças concede direitos de marca; NarrativeTrace é uma marca comercial da Empower
Agile.

### A licença, em palavras simples

Tudo o que é instalável a partir deste repositório é Business Source License 1.1 hoje; os
esquemas JSON são Apache 2.0 (veja schema/README.md).

<!-- legal:plain-words:begin -->
**Grátis para rodar.** O runtime é de código disponível sob a Business Source
License 1.1: você pode lê-lo, auditá-lo, corrigi-lo e usá-lo em produção sem
custo — inclusive dentro dos produtos e serviços que você vende aos seus
próprios clientes.

**Uma única exclusão.** Você não pode oferecer o próprio NarrativeTrace — ou um
produto ou serviço cujo valor derive substancialmente dele — a terceiros como
produto ou serviço de logging, tracing ou narrativa de código.

**Ela se abre em uma data.** Cada versão lançada se converte para Apache 2.0
quatro anos após ser publicada; a data exata é impressa no LICENSE daquela
versão.

*Este resumo é uma cortesia, não uma licença. O arquivo LICENSE é o único texto
vinculante; onde os dois divergirem, o LICENSE prevalece.*
<!-- legal:plain-words:end -->
