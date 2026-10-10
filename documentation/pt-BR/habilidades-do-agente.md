<!-- source: documentation/agent-skills.md blob e9b93aebce57 | translated: 2026-10-09 | reviewed: - -->

# Habilidades do agente

O NarrativeTrace inclui **habilidades** (*skills*): procedimentos carregáveis por um agente que
executam comandos testados e condicionam sua conclusão a um passo `verify`, em vez de
documentação que um agente pode ou não ler. Uma habilidade é deliberadamente enxuta — a lógica de
verificação, diagnóstico ou geração vive em código de biblioteca testado; o trabalho da própria
habilidade é saber quando agir, invocar esse código testado e interpretar o resultado no
contexto.

## Seis habilidades: configuração, diagnóstico, clareza, relatórios, verificação e depuração

- **`add-narrative-tracing`** — instala o NarrativeTrace em um projeto e o leva até seu primeiro
  trace: instala com o toolchain real (`uv add narrativetrace`), conecta os frameworks que o
  projeto já usa aplicando cada correção `config.<framework>-*` que o doctor imprime (a tabela de
  frameworks do próprio doctor instalado decide quais, então a página da habilidade não nomeia
  nenhum), envolve um objeto, renderiza e executa o primeiro trace, e então conecta um logger real (a ponte de `logging` da biblioteca
  padrão). Executa `uv run narrativetrace doctor` e passa adiante — a costura entre as duas
  habilidades — e termina *pré-visualizando* (nunca aplicando) `narrativetrace init`, para que a
  próxima sessão encontre essas habilidades já instaladas sem que ninguém precise dizer.
- **`narrativetrace-doctor`** — apenas diagnóstico, e **somente leitura**: nunca edita, gera ou
  exclui um arquivo. Executa a CLI testada, lê seu relatório e percorre as partes que uma simples
  saída de CLI não consegue cobrir sozinha: provar a ocultação em um teste, ler um trace
  renderizado antes de fazer asserções sobre ele, e o fluxo de aprovação de traces (marcado como
  não estudado — sua própria célula de avaliação ainda está pendente).
- **`add-narrativetrace-clarity`** — adiciona a um projeto o portão de clareza de nomes e o leva até
  ficar limpo: instala `narrativetrace-clarity` como dependência de desenvolvimento (`uv add
  --dev`), varre os pacotes do projeto, verifica que o relatório é **recente e pontuou ao menos uma
  classe** — a varredura termina com `0` e não escreve nada quando não encontra nenhuma classe,
  então um relatório antigo passaria por um novo —, renomeia o que o relatório sinaliza (em
  `snake_case`, seja qual for o estilo dos exemplos da sugestão), executa os testes do projeto e
  executa o portão de novo com os limites do próprio projeto até terminar com `0`. Nunca baixa um
  limite, nunca adiciona `--warn-only` e nunca colhe um glossário só para ler vocabulário. O
  portão deste runtime lê código-fonte Python, então não há caminho pelo executor de testes; um
  projeto que versiona um glossário executa a mesma varredura por
  `narrativetrace_glossary.clarity_scan`.
- **`narrativetrace-feedback`** — relata um defeito no próprio NarrativeTrace: uma verificação do
  doctor que está errada ou cuja correção não funciona, um passo de habilidade que não dá para
  seguir, uma redação do prompt de instalação que levou a um lugar errado, ou a biblioteca se
  comportando mal em um projeto bem configurado. O verbo testado por trás dela redige o relatório a
  partir do projeto (as coordenadas de instalação, o próprio relatório JSON do doctor e, no máximo,
  um trace estrutural), e **se recusa a escrever um relatório que carregue um valor dos seus
  traces** — nomeando a regra que o recusou, de modo que haja algo específico a corrigir em vez de
  um aviso a ignorar. Em seguida a habilidade mostra o rascunho inteiro e pergunta uma única vez se
  deve registrá-lo publicamente. Não envia nada a lugar nenhum e não registra nada sem uma resposta
  dada em um turno próprio.
- **`narrativetrace-verify`** — lê o que uma mudança realmente fez antes de o agente dizer que ela
  está pronta. Roda depois que os testes estão verdes e primeiro decide se vale a pena fazer o trace
  da mudança — uma função pura ou uma edição de uma única classe não vale, e a habilidade diz isso e
  para. Caso contrário, escreve a intenção antes de rodar qualquer coisa (quais colaboradores, em
  que ordem, em qual ramo, quantas vezes), roda o menor caminho real com o tracing ligado (um teste
  que usa a fixture `narrative_trace`), lê o trace estrutural sem valores contra essa intenção, abre
  valores só no span que parece errado, corrige e lê de novo, e então fixa o fluxo como baseline
  `.approved.nt` — liga o modo de aprovação se estiver desligado, roda a suíte inteira em modo de
  aprovação, mostra o `.received.nt` inteiro e só o promove com `narrativetrace-approve` depois do
  seu sim, num turno próprio. O relatório cita ids de span (`#2.1`), a posição que toda variante
  imprime para a mesma chamada, de modo que uma afirmação sobre o trace pode ser conferida contra o
  trace.
- **`narrativetrace-debug`** — encontra a causa de um resultado errado lendo o que o código fez com
  os valores, não percorrendo-o passo a passo. Começa de um sintoma, não de uma mudança: reproduz
  com a menor entrada e o tracing ligado, lê primeiro o diagrama de sequência quando o caminho
  cruza threads ou tasks, e então nomeia — pelo id de span, antes de mexer em qualquer código — o
  primeiro span cujas entradas estão certas e cujo resultado está errado. Estreita por span, nunca
  por arquivo: lê a subárvore sob esse id e, quando o trabalho dentro do span não tem trace, envolve
  mais um colaborador com `trace_object` em vez de ocultar qualquer coisa (`not_traced_field`,
  `__nt_not_traced__` e `@not_traced` ocultam um valor; não delimitam um trace). Corrige o defeito
  nesse span, roda de novo a mesma entrada e confere que nada mais se mexeu — uma execução vermelha
  não grava `.nt`, então a forma antes da correção são as linhas de chamada do Markdown da
  reprodução sem os valores. Mantém a reprodução como teste de regressão, fixa o trace estrutural
  dela pelo mesmo portão de aprovação do `narrativetrace-verify` e relata a causa raiz pelo id de
  span. Quando o trace e o código discordam, ou o defeito é do próprio NarrativeTrace, passa para o
  `narrativetrace-feedback` em vez de contornar o problema.

Elas se combinam: um projeto totalmente novo começa com `add-narrative-tracing`; um projeto que já
tem o NarrativeTrace instalado, onde algo não está funcionando, começa com
`narrativetrace-doctor`. Qualquer um dos caminhos termina no doctor — é ele quem possui o
diagnóstico a partir daí. `add-narrativetrace-clarity` é dona do relatório de nomes e de seu portão;
ela não instala o rastreamento. `narrativetrace-feedback` é onde um caminho termina quando o problema se
revela nosso e não do projeto — a regra de encerramento do próprio doctor aponta para ela.
`narrativetrace-verify` é o que uma sessão com o NarrativeTrace instalado faz depois de cada mudança
que mereça trace — o último passo da habilidade de instalação aponta a próxima sessão para ela, e o
achado `config.approval-mode` do doctor (baselines que nada compara) é corrigido pelo seu passo de
fixação. `narrativetrace-debug` é por onde começa um sintoma relatado; compartilha com a habilidade
de verificação a referência de leitura (qual variante responde a qual pergunta, e as formas que
indicam que algo deu errado) e a fixação, e termina no `narrativetrace-feedback` quando o defeito é
nosso. Uma habilidade posterior será responsável pela geração (escrever o teste
de prova de ocultação que hoje o doctor só pode pedir para você adicionar).

## A CLI `narrativetrace`

As duas primeiras habilidades executam `uv run narrativetrace doctor` — o verbo `doctor` da CLI
gratuita, ao lado de `init`/`uninstall` ([Instalando-as](#instalando-as), abaixo), `feedback` (o
verbo por trás de `narrativetrace-feedback`) e do script de console `narrativetrace-approve` já
existente. `doctor` é somente leitura, sem rede, `--json` para saída
legível por máquina, código de saída `0` (limpo), `1` (achados) ou `2` (não foi possível
executar). Dezenove verificações com identificadores estáveis e pontuados: as versões de
interpretador/pytest em relação ao que é declarado, os oito pacotes `narrativetrace-*`
concordando em uma única versão, a grafia de `NARRATIVETRACE_OUTPUT`, o registro do plugin do
pytest, se as habilidades do agente do NarrativeTrace estão instaladas e atualizadas, chaves
desconhecidas em `narrativetrace.toml`, um marcador de ocultação importado mas nunca usado, os
parâmetros de um método `*args` colapsando em um único valor `args: [...]`, se a
ocultação está comprovada em um teste, diffs de traces de aprovação obsoletos, baselines aprovadas que nada compara
porque o modo de aprovação está desligado, e uma verificação
`config.<framework>-*` por linha da tabela de frameworks (a tabela e a conexão de cada linha estão
em [`llms-full.md`](../llms-full.md#framework-table--what-the-doctor-checks)): um framework que o
projeto usa cuja integração não foi adicionada, ou foi adicionada mas nunca conectada, falha com
as linhas a adicionar; um framework sem integração publicada é informado, nunca adivinhado.

`feedback draft | url | gh` tem três canais sobre um mesmo relatório. `draft` escreve o relatório em
`build/narrativetrace/feedback/` e o imprime inteiro; `url` imprime a URL pré-preenchida do
formulário de issues de `github.com/narrativetrace/narrativetrace-python`, que você abre e envia
com a sua própria conta; `gh` imprime a linha exata de `gh issue create`, somente quando o `gh` está
instalado e autenticado, e nunca a executa. Cada canal redige de novo a partir das opções que
recebe, então nada é registrado sob um rascunho que mudou depois de ser mostrado. Código de saída
`0` (redigido), `1` (o canal não está disponível, ou o sistema de arquivos recusou os arquivos) ou
`2` (uma regra `vf.*` livre de valores recusou o relatório e nada foi escrito; ou a linha de comando
não pôde ser lida). Registrar é público: mostra que o seu projeto usa o NarrativeTrace.

## Instalando-as

O pacote `narrativetrace` (que `uv add narrativetrace` já coloca no seu `PATH`) carrega um verbo
`init` que instala as seis habilidades para você — sem rede, e sem escrever nada até você mandar:

```bash
uv run narrativetrace init --dry-run
```

<!-- snippet: examples/sixty_seconds/build/agent-skills-init-preview.json -->
```json
{
  "carrier": "narrativetrace-skills==0.3.0",
  "actions": [
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-doctor/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/add-narrative-tracing/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-feedback/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/add-narrativetrace-clarity/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-verify/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-debug/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": "AGENTS.md",
      "status": "planned"
    }
  ],
  "exit_code": 0
}
```
<!-- /snippet -->

Esse é o envelope `--json`; sem a opção, o mesmo comando imprime o plano como um diff unificado.
Leia-o, e então execute-o de novo sem `--dry-run` para escrever `.agents/skills/` (e também
`.claude/skills/`, assim que este projeto tiver um diretório `.claude/` ou um `CLAUDE.md`, ou com
`--vendor claude`) mais uma seção marcada em `AGENTS.md`. `narrativetrace uninstall` remove
exatamente o que ele escreveu e mais nada; a verificação `config.skills-installed` do
`narrativetrace doctor` avisa quando o que está instalado fica desatualizado, então mantê-lo em
dia depois é rodar `init --dry-run` de novo, não copiar os arquivos à mão outra vez.

Copiar os arquivos renderizados à mão ainda funciona, e é o caminho alternativo para uma
plataforma sem convenção própria de descoberta, ou antes de você ter adicionado o pacote
`narrativetrace`:

- **Claude Code**: os arquivos `SKILL.md` renderizados vivem em
  [`.claude/skills/add-narrative-tracing/`](../../.claude/skills/add-narrative-tracing/SKILL.md),
  [`.claude/skills/narrativetrace-doctor/`](../../.claude/skills/narrativetrace-doctor/SKILL.md),
  [`.claude/skills/narrativetrace-feedback/`](../../.claude/skills/narrativetrace-feedback/SKILL.md),
  [`.claude/skills/add-narrativetrace-clarity/`](../../.claude/skills/add-narrativetrace-clarity/SKILL.md),
  [`.claude/skills/narrativetrace-verify/`](../../.claude/skills/narrativetrace-verify/SKILL.md) e
  [`.claude/skills/narrativetrace-debug/`](../../.claude/skills/narrativetrace-debug/SKILL.md)
  neste repositório — o nome do diretório e o `name:` do frontmatter são sempre o id canônico do
  catálogo, nunca um segmento abreviado: um diretório `.claude/skills/` no nível do repositório é
  um namespace plano, não um plugin do Claude, então um nome abreviado (`doctor`) colidiria com a
  habilidade de qualquer outro fornecedor com esse mesmo nome. Copie qualquer um dos diretórios
  para o `.claude/skills/<nome>/` do seu próprio projeto e o Claude o reconhece sozinho, invocável
  pelo nome (`add-narrative-tracing` / `narrativetrace-doctor` / `narrativetrace-feedback` /
  `add-narrativetrace-clarity` / `narrativetrace-verify` / `narrativetrace-debug`) diretamente.
- **Codex CLI**: os arquivos `SKILL.md` renderizados vivem em
  [`.agents/skills/add-narrative-tracing/`](../../.agents/skills/add-narrative-tracing/SKILL.md),
  [`.agents/skills/narrativetrace-doctor/`](../../.agents/skills/narrativetrace-doctor/SKILL.md),
  [`.agents/skills/narrativetrace-feedback/`](../../.agents/skills/narrativetrace-feedback/SKILL.md),
  [`.agents/skills/add-narrativetrace-clarity/`](../../.agents/skills/add-narrativetrace-clarity/SKILL.md),
  [`.agents/skills/narrativetrace-verify/`](../../.agents/skills/narrativetrace-verify/SKILL.md) e
  [`.agents/skills/narrativetrace-debug/`](../../.agents/skills/narrativetrace-debug/SKILL.md)
  neste repositório — a própria documentação de descoberta de habilidades do Codex (verificada em
  2026-09-14) varre `.agents/skills/<name>/SKILL.md` a partir do diretório de trabalho até a raiz
  do repositório, então é exatamente aí que ele os encontra, com os mesmos nomes de diretório
  canônicos do Claude Code acima. O frontmatter carrega apenas `name` e `description` — os dois
  campos que o Codex documenta — o corpo da página abaixo é idêntico, byte a byte, ao do Claude
  Code.
- **Qualquer agente, qualquer plataforma**: todo agente que lê o `AGENTS.md` vê o ponteiro sempre
  ativo que o próprio `AGENTS.md` deste repositório carrega entre seus marcadores
  `<!-- narrativetrace:skills:start -->` — o nome e a descrição de cada habilidade, então um
  agente que nunca pensou em procurar por elas ainda assim sabe que existem.
- **Gemini** ainda não tem uma convenção de descoberta de habilidades — está no roteiro, não
  construída.

## A partir de um registro

Um projeto pode carregar essas habilidades sem que ninguém aqui jamais tenha executado `init`, em
um de três estados:

1. **Instalado pelo `init`** — commitado, do time. O único estado que `config.skills-installed`
   aprova: as páginas carregam a linha de procedência e correspondem ao release que este projeto
   resolve.
2. **Uma instalação pessoal a partir de um registro** (um cache de plugins do Claude Code) — só
   sua. Invisível para o doctor por design: ele diagnostica o projeto, e uma instalação pessoal não
   alcança nenhum colega de equipe nem nenhum outro agente.
3. **Uma instalação de registro no projeto** (`npx skills add`) — as próprias páginas renderizadas
   deste repositório, levadas por um registro em vez de pelo `init`, então ainda não carregam linha
   de procedência.

Experimentando as habilidades você mesmo, sem tocar no projeto:

```text
/plugin marketplace add narrativetrace/narrativetrace-python
/plugin install narrativetrace-python@narrativetrace-python
```

depois rode `uv run narrativetrace init --dry-run`, leia o diff, e rode-o sem a flag para que o
`AGENTS.md` aponte para elas.

Instalando no projeto a partir do registro do padrão aberto:

```text
npx skills add narrativetrace/narrativetrace-python
```

depois rode `uv run narrativetrace init --dry-run`, leia o diff, e rode-o sem a flag para que o
`AGENTS.md` aponte para elas.

Uma página que um registro deixou para trás nunca é recusada só por estar lá. O `init` a compara,
byte a byte exceto pela quebra de linha, com o que ele mesmo teria renderizado. Uma idêntica à
própria página deste release é **adotada** — é o que o plano diz, em vez de "substituída", porque
quem lê precisa saber que nada seu foi sobrescrito. Este é o próprio texto do plano, citado, nunca
digitado de novo aqui:

<!-- snippet: packages/narrativetrace-tooling/src/narrativetrace_tooling/init/plan_renderer.py region=adoptedNote -->
```python
ADOPTED = "adopted: identical to this carrier's page, so only the provenance line is added"
"""What the plan and the report say about a page that was already ours in everything but a line."""

```
<!-- /snippet -->

Uma página que difere — outro release, ou editada à mão — mantém a recusa comum para a qual
existe o `--force`. O `npx skills add` também deixa `.claude/skills/<nome>` como um link simbólico
para a página do padrão aberto; o `init` nunca escreve através de um link desses. Um link cujo
alvo ele adotaria ou já é dele é substituído por um diretório real com o flavor certo; qualquer
outro link é recusado, porque `--force` cobre conteúdo, nunca um link.

E este é o próprio reparo do doctor, citado da mesma forma, para um projeto onde as páginas estão
lá mas não carregam nada disso:

<!-- snippet: packages/narrativetrace-tooling/src/narrativetrace_tooling/doctor/checks/skills_installed.py region=registryMessages -->
```python
_INIT_COMMAND = "uv run narrativetrace init --dry-run"

_READ_THE_DIFF = f"Run `{_INIT_COMMAND}`, read the diff, then run it without the flag."

_FROM_A_REGISTRY = (
    " Pages that are there without our line usually came from a registry (npx skills add, a plugin"
    " or workspace install). A page identical to this release's is adopted, and no --force is"
    " needed."
)
"""What a page with no provenance line most often IS: a registry install of this repository's own
rendered pages (design D5 state 3). Naming the case matters because the obvious reading of "not
ours" is "somebody else's work", which invites a ``--force`` nobody needs."""

```
<!-- /snippet -->

## Como são construídas

Nenhuma habilidade é editada manualmente.
`packages/narrativetrace-skills-catalogue/src/narrativetrace_skills/catalogue/add_narrative_tracing.py`,
`.../catalogue/narrativetrace_doctor.py`, `.../catalogue/narrativetrace_feedback.py` e
`.../catalogue/add_narrativetrace_clarity.py` são as fontes
da verdade; `python scripts/skills_render.py --fix` regenera o `.claude/skills/<nome>/SKILL.md` de
cada habilidade, seu equivalente de Codex em `.agents/skills/`, a própria seção do `AGENTS.md` deste repositório, e `.claude-plugin/marketplace.json` — a listagem
que faz deste repositório um marketplace de plugins do Claude Code — a partir delas, e `python
scripts/skills_render.py --check` (integrado ao `uv run poe check`) falha a build no momento em
que qualquer um deles se desalinha da fonte tipada. Todo bloco de código
que uma página renderizada mostra é incorporado a partir de código-fonte real e testado, através
da mesma convenção de marcador `<!-- snippet: -->` que o restante da documentação deste
repositório já usa — nunca um exemplo digitado manualmente. Uma verificação de Tier A mantém
citações a notas de planejamento privadas fora de todas as páginas: frases de justificativa são
publicadas, a citação que nomeia a nota não. Uma segunda verificação guarda a única linha de
frontmatter cuja ausência é uma virtude: uma habilidade cujos passos podem tornar algo público —
hoje, `narrativetrace-feedback` — não deve declarar `allowed-tools`, porque esse campo pré-aprova as
ferramentas listadas durante o turno que carrega a habilidade, e uma habilidade de relatórios que
pré-aprovasse o seu próprio comando de relatório deixaria o arnês de perguntar exatamente onde
perguntar é o ponto. A página do Claude Code de uma habilidade assim não tem nenhuma linha
`allowed-tools`, em vez de uma vazia. Uma terceira verificação submete à mesma regra, pelo mesmo
motivo, uma habilidade que promove uma baseline de aprovação — hoje, `narrativetrace-verify` e
`narrativetrace-debug`: a promoção roda por `uv run narrativetrace-approve`, e o sim que ela espera
é o seu.

## Avaliando-as

`packages/narrativetrace-skills-catalogue/evals/` carrega a suíte de Tier B (frases de gatilho, um
caso de caminho feliz por habilidade, um caso de desvio para a verificação de ocultação do doctor; o caminho feliz da habilidade de clareza parte de um fixture cujos nomes pouco
claros o portão sinaliza, e é avaliado por o portão passar limpo depois)
— nunca executada por `poe check`; o responsável a executa manualmente ou a partir do job noturno,
por meio de CLIs de assinatura, nunca a API medida. Veja o [próprio
README](../../packages/narrativetrace-skills-catalogue/evals/README.md) para a política dos
carris esporádicos (Codex/Gemini) e a matriz de promoção.

## Veja também

- [`narrativetrace-skills-catalogue`](../../packages/narrativetrace-skills-catalogue/README.md) —
  o pacote do catálogo tipado
- [Sessenta segundos](sessenta-segundos.md) — o passo a passo de instalação e primeiro trace do
  qual os passos do `add-narrative-tracing` são extraídos
- [O que commitar](o-que-commitar.md) — o estado das traces de aprovação que o quarto passo do
  doctor verifica
- [Privacidade e ocultação](privacidade-e-ocultacao.md) — a lista de negação e os formatos de valor
  contra os quais as próprias regras livres de valores do relatório de problemas são medidas
