<!-- source: documentation/feature-guide.md blob b2f5f3a14c42 | translated: 2026-09-07 | reviewed: - -->

# Guia de funcionalidades do NarrativeTrace (Python)

O que o NarrativeTrace para Python distribui, da perspectiva de quem usa. Para o catálogo
completo de funcionalidades multiplataforma (todos os níveis, todas as
plataformas), veja o guia de funcionalidades canônico:
<https://github.com/narrativetrace/narrativetrace-java/blob/main/documentation/feature-guide.md>.

**Rótulos de status** (mesmo vocabulário do guia canônico):

- **Gratuito** — lançado e disponível neste repositório, sob a Business
  Source License 1.1 (veja *Licenciamento* abaixo).
- **Pro** — lançado no NarrativeTrace Pro (nível comercial, uma
  distribuição separada).
- **Em desenvolvimento** — sendo construído ativamente; o design já está
  definido.
- **Planejado** — especificado, ainda não iniciado; pode mudar.

**Licenciamento.** A API e o formato de saída do NarrativeTrace são padrões
abertos (Apache 2.0). Seu runtime é gratuito e de código disponível (BSL 1.1,
convertendo para Apache 2.0 quatro anos após cada versão). Pro é comercial.
Tudo marcado como **Gratuito** aqui é esse runtime: livre para usar em
produção, de código disponível, não open source — a [`LICENSE`](../../LICENSE) raiz é
a autoridade.

A documentação por tópico vive em [guides/](../guides). O *porquê* por trás
dos mecanismos específicos do Python — incluindo alternativas rejeitadas — é
registrado como um log de decisões interno, não publicado aqui.

---

## Capture a história do seu código (tracing principal)

| Funcionalidade | Status | Notas |
|---|---|---|
| Captura narrativa automática — nomes de método, classe e parâmetro, valores de retorno, timing, erros; zero declarações de log | Gratuito | `trace_object(obj, context)` + `ContextVarNarrativeContext`; nomes lidos via `inspect.signature` |
| Decoradores de enriquecimento — `@narrated("… {param} …")`, `@on_error(ExcType, "…")` empilhável (o mais específico vence), sobrescritas de nome `@traced` para `*args`, `@narrative_summary` | Gratuito | [guides/decorators.md](guia-de-decoradores.md) |
| Ocultação de dados sensíveis — parâmetros `@not_traced`, campos `not_traced_field(...)` / `__nt_not_traced__`, ocultação por padrão de nome (`RedactionPolicy`) | Gratuito | Valores ocultos renderizam como `[REDACTED]`, nunca lidos de forma alguma para membros marcados; um caminho de template `@narrated`/`@on_error` que alcança um membro oculto resolve para o mesmo marcador, em qualquer profundidade do caminho; um `NamedTuple` é introspectado pelo nome do campo em vez de impresso como uma coleção posicional anônima, então um campo oculto permanece oculto um nível de container a mais também |
| Cinco níveis de captura (OFF → ERRORS → SUMMARY → NARRATIVE → DETAIL), alteráveis em tempo de execução, canal de ambiente `NARRATIVETRACE_LEVEL` | Gratuito | Os nomes de nível diferem da implementação Java (SUMMARY/NARRATIVE vs. NARRATIVE/FLOW). Valores de parâmetro só existem em DETAIL; a supressão acontece na captura, não na renderização |
| Níveis de dois portões — nível de captura e nível de log são independentes | Gratuito | [guides/configuration.md](guia-de-configuracao.md) |
| Captura de concorrência — `ForkJoinGroup` / `FireAndForgetGroup` sobre tasks do asyncio *e* `ThreadPoolExecutor`, propagação de snapshot de identidade completa, enxerto entre tasks | Gratuito | A história permanece coerente quando a execução não é sequencial |
| Propagação bidirecional — um snapshot leva o trace *para dentro* de uma thread ou task, e o trabalho traçado ali *volta*: a pilha que captura reporta a partir do momento em que é publicado, transitivamente através de uma cadeia de saltos async | Gratuito | O posicionamento segue o momento do submit; trabalho adotado é marcado `ConcurrencyKind.ASYNC`; helpers que reemitem seus próprios filhos optam por sair com `activate_without_adoption()`; limitado a 10.000 spans por pilha, entregas acima do limite são recusadas por inteiro e reportadas via `TraceLoss` |
| Identidade de trace — id de trace, nomes de trace legíveis por humanos, derivação de id de história/capítulo | Gratuito | Alinhado ao esquema canônico |
| Contrato de pureza — a introspecção enumera dados armazenados; getters `@property` nunca executam; todo membro invocado é limitado e isolado de exceções | Gratuito | [guides/decorators.md](guia-de-decoradores.md) |
| Captura à prova de falhas — um renderizador ou exportador que lança exceção nunca esconde o resultado de negócio ou a exceção (métodos síncronos e `async`) | Gratuito | |

## Conecte ao seu stack (integrações)

| Funcionalidade | Status | Notas |
|---|---|---|
| Envolvimento explícito de objetos — `trace_object(...)` | Gratuito | Sem import hooks, sem monkey-patching; veja o ADL da plataforma |
| Plugin do pytest — fixture `narrative_trace`, narrativas de falha, avisos de template, artefatos por teste, resumo de suíte | Gratuito | Se autorregistra via entry point; [guides/pytest.md](guia-de-pytest.md) |
| Middleware ASGI (Starlette/FastAPI) — captura/exportação no limite da requisição, metadados de requisição e usuário, caminhos excluídos, adoção de `traceparent` W3C | Gratuito | [guides/fastapi-asgi.md](guia-de-fastapi-asgi.md) |
| Acessor de contexto com escopo de requisição — `get_narrative_context()` (utilizável como `Depends` do FastAPI) | Gratuito | |
| Injeção de `traceparent` de saída para `httpx` (hooks síncronos e async) | Gratuito | Extra exclusivo do Python; fecha o loop entre serviços |
| Middleware WSGI (Flask) | Planejado (Gratuito) | Mesmo contrato de limite de requisição do ASGI |
| Middleware do Django | Planejado (Gratuito) | Mesmo contrato de limite de requisição do ASGI |

ASGI é a única integração web lançada hoje — Flask/WSGI e Django estão
Planejados, não apenas sem documentação.

## Leia a história (saídas)

| Funcionalidade | Status | Notas |
|---|---|---|
| Renderizadores de texto indentado, Markdown e prosa | Gratuito | |
| Referências de valor de trace — deduplicação endereçada por conteúdo de valores capturados repetidos, com rótulos legíveis (`‹Hotel›=full` na primeira emissão, `‹Hotel›` depois) | Gratuito | `render.value_reference.ValueReferenceIndex` via `MarkdownRenderer`. Rótulos vêm do campo de identidade do valor estruturado (name/id/description/…), nunca de um oculto; igualdade de bytes certifica igualdade; contenção dentro de outros valores capturados conta e é substituída. Somente Markdown |
| Deltas de valor intra-trace — uma recaptura da mesma entidade, alterada, renderiza como um diff contra a referência (`‹Dinner›′{amount: 100.0→92.0, currency: "USD"→"EUR"}`) | Gratuito | `render.value_delta.value_delta`. "Mesma entidade" é o mesmo nome de tipo estruturado mais um campo de identidade igual; apenas campos escalares alterados (`StringVal`/`IntVal`/`FloatVal`/`BoolVal`/`InstantVal`/`NullVal`), nunca reconstruídos a partir da árvore estruturada. Um objeto aninhado ou lista alterados, um conjunto de campos diferente, ou um valor sem campo de identidade renderiza por completo exatamente como antes. Uma variante alterada que por si só se repete é definida COMO o diff (`‹Dinner·2›=‹Dinner›′{…}`). Somente Markdown |
| Arquivos de trace por teste com companheiros `.json` e Mermaid `.mmd` | Gratuito | `NARRATIVETRACE_OUTPUT=1`; traces vazios não gravam nada |
| Exportação JSON canônica (forma de stream de eventos) | Gratuito | `export_json` / `export_document_json`; testado com round-trip, e validado por esquema contra `chapter-tree.schema.json` a partir dos bytes que o writer real gravou em disco |
| Esquema de capítulo por serviço (`nt.entryType` / `schemaVersion` / entradas história-capítulo) | Gratuito | `export_chapter_json`; validado contra `chapter.schema.json`. A correlação nunca é omitida: `trace_id` é adotado/herdado/gerado, `nt.storyId` recai na primeira chamada raiz (`Class.method`, senão `unknown`), `nt.chapterId` na história, `nt.traceName` no id resolvido — então um trace capturado sem nenhum span ainda assim valida |
| Esquema canônico **1.2** — um único `SCHEMA_VERSION` para a forma de entrada, o envelope de capítulo e os atributos do OTel | Gratuito | `nt.narrationTemplate` (1.1, o texto bruto do `@narrated` com marcadores intactos) mais os campos de identidade 1.2: `nt.package`, `nt.exceptionPackage`, `nt.returnType`, `type` de parâmetro, `thread.name`/`thread.id`/`nt.threadVirtual`. `nt.instanceId`, `code.filepath`/`code.lineno` e os campos de recurso de processo estão declarados mas não capturados (registrado na lista de tarefas privada) — os três também vêm desligados por padrão em Java |
| `.canonical.json` por teste — o array plano de entradas, um enter + um exit por chamada | Gratuito | `NARRATIVETRACE_CANONICAL=1`, independente de `format`. Árvores sem contexto recebem ids de span sequenciais e um id de trace **gerado** (identidade antecipada, ADR-014 do produto): ids de span, história e capítulo são derivados e estáveis em bytes entre execuções, enquanto `trace_id`/`nt.traceName` são únicos por captura e devem ser dobrados pelo normalizador de conformidade antes de comparar os goldens |
| Diagramas de sequência — Mermaid + PlantUML | Gratuito | `narrativetrace-diagrams` |
| Visualizações de tradução de trace — renderiza novamente um trace capturado em um idioma que o `glossary.json` commitado cobre; identificadores traduzidos com o original mantido ao lado, valores e mensagens de exceção idênticos byte a byte, ocultação intacta, um rodapé de "lacunas do glossário" nomeia toda frase deixada sem tradução | Gratuito | `narrativetrace-glossary`; streaming ao vivo via `TranslationSubscriber` (um observador do pipeline ao lado do caminho durável do próprio trace, nunca uma substituição) ou um arquivo por trace via `TranslationFileSink`; `./demo.sh --example <name> --lang es\|zh-CN` é o exemplo incluído |
| Resumos de teste no console com pontuações de clareza | Gratuito | |
| Resumos de fluxo — caminhos agregados + frequências por ponto de entrada | Planejado (Pro, restrito) | Fase E3 do plano Enterprise |
| Diffs de migração — comparação comportamental antes/depois | Planejado (Pro, restrito) | Fase E3 do plano Enterprise |
| Grafos de dependência em tempo de execução (sempre chamado vs. condicional) | Planejado (Pro, restrito) | Fase E4 do plano Enterprise |

## Mantenha seu stack de logging (logging + observabilidade)

| Funcionalidade | Status | Notas |
|---|---|---|
| Ponte com `logging` da stdlib — eventos narrativos através dos seus handlers existentes sob o logger `narrativetrace`, sobrescritas de nível por tipo de evento | Gratuito | Enter/return em DEBUG, exceções em WARNING; [guides/logging.md](guia-de-logging.md) |
| Enriquecimento estilo MDC — `NarrativeContextFilter` estampa chaves canônicas de correlação em todo registro; `request_log_scope` para chaves em nível de requisição | Gratuito | `traceId`/`spanId`/`nt.class`/`nt.method`/`nt.depth`/identidade do serviço |
| Processador de structlog emitindo o mesmo conjunto de chaves | Gratuito | `narrativetrace-structlog`; fonte única de vocabulário (`current_scope_keys()`) |
| Coexistência com logs escritos à mão | Gratuito | Remova-os no seu próprio ritmo |
| Exportação de spans do OpenTelemetry — listener de eventos ao vivo + exportador de árvore em lote, atributos `narrative.*` tipados, despejo de órfãos | Gratuito | `narrativetrace-otel`; [guides/opentelemetry.md](guia-de-opentelemetry.md) |
| Pipeline de eventos — fan-out de caminho duplo, buffer limitado, consumidor com thread de drenagem com watchdog e descarte sob carga | Gratuito | Buffering/retenção é gratuito por design (ADR-010 do produto) |
| Agregação de stream de eventos — árvore agregada, hotspots, caminhos/taxas de erro, frequências de método/erro (`EventAggregator`) | Pro | Realocado em 12/07/2026 (Fase 31a) para a distribuição comercial; alimente-o com `EventStore.events()` |

## Melhore o código (diagnósticos de clareza)

| Funcionalidade | Status | Notas |
|---|---|---|
| Pontuação de clareza — qualidade de nomes de método/classe/parâmetro a partir de traces reais (cinco avaliadores ponderados, dicionários idênticos byte a byte ao Java) | Gratuito | [guides/clarity.md](guia-de-clareza.md) |
| Divisão de clareza em nível de suíte + `clarity-results.json` / `clarity-report.md` via o plugin do pytest | Gratuito | |
| Scanner de fonte independente — script de console `narrativetrace-clarity`, sem exigir testes | Gratuito | |
| Vocabulário de projeto na pontuação — o glossário commitado estende os dicionários embutidos | Gratuito | Um arquivo, um fluxo de revisão: verbos do `glossary.json` commitado pontuam como verbos de domínio, seus substantivos como tokens de domínio. Lido de `narrativetrace.glossary_dir` (padrão: diretório de trabalho) uma vez por sessão; a leitura é incondicional, ao contrário da coleta. Os níveis embutidos mantêm autoridade — verbos genéricos, prefixos booleanos, marcadores sem significado, sinônimos obsoletos e termos `stale` nunca são promovidos |
| Abreviações aceitas — uma seção `abbreviations` declarada em nível raiz do `glossary.json` | Gratuito | Esquema 2: `{"fx": "foreign exchange"}`. Só um token listado deixa de ser solicitado a ser escrito por extenso — um token que aparece dentro de um termo commitado não, então `calc total` mantém a dica `calc` → `calculate`. De propriedade humana (a coleta nunca a escreve, a mesclagem a mantém intacta); omitida quando vazia, então um glossário que não declara nenhuma permanece idêntico byte a byte ao esquema 1; leitores a aceitam em qualquer versão |
| Coleta de vocabulário — hook da suíte do pytest (opt-in pela presença de `glossary.json`, `NARRATIVETRACE_GLOSSARY=off/on` sobrepõe) mescla termos novos e sinaliza usos de aliases obsoletos como issues de clareza `non-canonical-term`, cada uma com uma sugestão de renomeação mecânica | Gratuito | Mesclagem somente aditiva (campos de autoria humana nunca são sobrescritos); um `glossary-usage.json` volátil relata o que uma execução encontrou, nunca commitado |
| Varredura estática do glossário — script de console `glossary-scan`, sem exigir execução de testes; também é o único lugar onde templates de narração `@narrated`/`@on_error` são coletados (um trace capturado já tem os valores interpolados) | Gratuito | `narrativetrace-glossary`; uma ferramenta de escrita deliberada e opt-in, não um gate de CI |
| Gate de CI opcional — `--min-score`, `--max-high-issues` | Gratuito | Consultivo por padrão é o recomendado |

## Deixe agentes de IA verem a verdade em tempo de execução (integração com IA)

| Funcionalidade | Status | Notas |
|---|---|---|
| Documentação orientada a LLM (`llms.txt`, `llms-full.md`) | Gratuito | |
| Handlers de ferramentas de análise MCP | Planejado (Pro, restrito) | Fase E5 do plano Enterprise |

Nota: a separação de valores acontece no momento da captura (ADR-002 do
produto — abaixo de DETAIL, valores de parâmetro nunca são registrados),
mas o segundo arquivo de trace *estrutural* seguro para IA por teste do
implementação Java ainda não tem equivalente em Python; o plugin do pytest grava um
único arquivo com detalhe completo por teste.

## Nível Pro (comercial)

O nível Pro do Python é distribuído como uma distribuição comercial
separada (licença proprietária, nunca publicada no PyPI). A agregação de stream de eventos foi realocada
para lá a partir do core gratuito deste repositório em 12/07/2026 (Fase 31a
Etapa 2): **`EventAggregator` — Pro**. Resumos de fluxo, diffs de migração,
diagramas de grafo de dependência, e handlers de ferramentas MCP estão
**Planejados (Pro, restrito)** — a execução aguarda um contrato pago no
stack Python conforme o plano de implementação privado desse
repositório (Fases E3–E5). Auditoria & conformidade **não
está planejado** para Python (Fase E6).

---

## Mantendo este guia honesto

Adaptado das regras do guia canônico:

1. Toda funcionalidade visível ao usuário do NarrativeTrace para Python aparece aqui,
   exatamente uma vez, com um status.
2. Uma funcionalidade só passa para **Gratuito**/**Pro** quando está
   mesclada (merged), testada e documentada. "Em desenvolvimento" significa
   que o design já está definido e o trabalho está agendado; "Planejado"
   significa que só está especificado.
3. Mudanças que adicionam ou promovem uma funcionalidade devem atualizar
   este arquivo no mesmo commit.
4. Este guia cobre apenas o que o NarrativeTrace para Python distribui. Funcionalidades de
   todo o produto e seus status multiplataforma vivem no guia canônico
   (linkado no topo) — não bifurque suas linhas aqui; registre somente a
   realidade do lado Python (incluindo as lacunas, com honestidade).
