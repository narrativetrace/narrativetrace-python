<!-- source: documentation/agent-skills.md blob e2bcca43b6fa | translated: 2026-09-14 | reviewed: - -->

# Habilidades do agente

*(since 0.1.2, unreleased)*

O NarrativeTrace inclui **habilidades** (*skills*): procedimentos carregáveis por um agente que
executam comandos testados e condicionam sua conclusão a um passo `verify`, em vez de
documentação que um agente pode ou não ler. Uma habilidade é deliberadamente enxuta — a lógica de
verificação, diagnóstico ou geração vive em código de biblioteca testado; o trabalho da própria
habilidade é saber quando agir, invocar esse código testado e interpretar o resultado no
contexto.

## Duas habilidades: configuração e diagnóstico

- **`add-narrative-tracing`** — instala o NarrativeTrace em um projeto e o leva até seu primeiro
  trace: instala com o toolchain real (`uv add narrativetrace`), envolve um objeto, renderiza e
  executa o primeiro trace, e então conecta um logger real (a ponte de `logging` da biblioteca
  padrão). Termina executando `uv run narrativetrace doctor` e passando adiante — a costura entre
  as duas habilidades.
- **`narrativetrace-doctor`** — apenas diagnóstico, e **somente leitura**: nunca edita, gera ou
  exclui um arquivo. Executa a CLI testada, lê seu relatório e percorre as partes que uma simples
  saída de CLI não consegue cobrir sozinha: provar a ocultação em um teste, ler um trace
  renderizado antes de fazer asserções sobre ele, e o fluxo de aprovação de traces (marcado como
  não estudado — sua própria célula de avaliação ainda está pendente).

Elas se combinam: um projeto totalmente novo começa com `add-narrative-tracing`; um projeto que já
tem o NarrativeTrace instalado, onde algo não está funcionando, começa com
`narrativetrace-doctor`. Qualquer um dos caminhos termina no doctor — é ele quem possui o
diagnóstico a partir daí. Uma habilidade posterior será responsável pela geração (escrever o teste
de prova de ocultação que hoje o doctor só pode pedir para você adicionar).

## A CLI `narrativetrace`

Ambas as habilidades executam `uv run narrativetrace doctor` — o verbo `doctor` da CLI gratuita,
ao lado do script de console `narrativetrace-approve` já existente. Somente leitura, sem rede,
`--json` para saída legível por máquina, código de saída `0` (limpo), `1` (achados) ou `2` (não
foi possível executar). Onze verificações com identificadores estáveis e pontuados: as versões de
interpretador/pytest em relação ao que é declarado, os oito pacotes `narrativetrace-*`
concordando em uma única versão, a grafia de `NARRATIVETRACE_OUTPUT`, o registro do plugin do
pytest, chaves desconhecidas em `narrativetrace.toml`, um marcador de ocultação importado mas
nunca usado, os parâmetros de um método `*args` colapsando em um único valor `args: [...]`, se a
ocultação está comprovada em um teste, e diffs de traces de aprovação obsoletos.

## Instalando-as

- **Claude Code**: os arquivos `SKILL.md` renderizados vivem em
  [`.claude/skills/add-narrative-tracing/`](../../.claude/skills/add-narrative-tracing/SKILL.md) e
  [`.claude/skills/narrativetrace-doctor/`](../../.claude/skills/narrativetrace-doctor/SKILL.md)
  neste repositório — o nome do diretório e o `name:` do frontmatter são sempre o id canônico do
  catálogo, nunca um segmento abreviado: um diretório `.claude/skills/` no nível do repositório é
  um namespace plano, não um plugin do Claude, então um nome abreviado (`doctor`) colidiria com a
  habilidade de qualquer outro fornecedor com esse mesmo nome. Copie qualquer um dos diretórios
  para o `.claude/skills/<nome>/` do seu próprio projeto e o Claude o reconhece sozinho, invocável
  pelo nome (`add-narrative-tracing` / `narrativetrace-doctor`) diretamente.
- **Codex CLI**: os arquivos `SKILL.md` renderizados vivem em
  [`.agents/skills/add-narrative-tracing/`](../../.agents/skills/add-narrative-tracing/SKILL.md) e
  [`.agents/skills/narrativetrace-doctor/`](../../.agents/skills/narrativetrace-doctor/SKILL.md)
  neste repositório — a própria documentação de descoberta de habilidades do Codex (verificada em
  2026-09-14) varre `.agents/skills/<name>/SKILL.md` a partir do diretório de trabalho até a raiz
  do repositório, então é exatamente aí que ele os encontra, com os mesmos nomes de diretório
  canônicos do Claude Code acima. O frontmatter carrega apenas `name` e `description` — os dois
  campos que o Codex documenta — o corpo da página abaixo é idêntico, byte a byte, ao do Claude
  Code.
- **Qualquer agente, qualquer plataforma**: todo agente que lê o `AGENTS.md` vê o ponteiro sempre
  ativo que o próprio `AGENTS.md` deste repositório carrega entre seus marcadores
  `<!-- narrativetrace:skills:start -->` — os nomes e descrições de ambas as habilidades, então um
  agente que nunca pensou em procurar por elas ainda assim sabe que existem.
- **Gemini e um instalador automático** estão no roteiro mas ainda não foram construídos — hoje,
  copiar os arquivos renderizados é o caminho para qualquer plataforma sem convenção própria de
  descoberta.

## Como são construídas

Nenhuma habilidade é editada manualmente.
`packages/narrativetrace-skills/src/narrativetrace_skills/catalogue/add_narrative_tracing.py` e
`.../catalogue/narrativetrace_doctor.py` são as duas fontes da verdade; `python
scripts/skills_render.py --fix` regenera `.claude/skills/add-narrative-tracing/SKILL.md`,
`.claude/skills/narrativetrace-doctor/SKILL.md`, seus equivalentes de Codex em `.agents/skills/`
e a própria seção do `AGENTS.md` deste repositório a partir delas, e `python
scripts/skills_render.py --check` (integrado ao `uv run poe check`) falha a build no momento em
que qualquer um dos cinco se desalinha da fonte tipada. Todo bloco de código
que uma página renderizada mostra é incorporado a partir de código-fonte real e testado, através
da mesma convenção de marcador `<!-- snippet: -->` que o restante da documentação deste
repositório já usa — nunca um exemplo digitado manualmente. Uma verificação de Tier A mantém
citações a notas de planejamento privadas fora das duas páginas: frases de justificativa são
publicadas, a citação que nomeia a nota não.

## Avaliando-as

`packages/narrativetrace-skills/evals/` carrega a suíte de Tier B (frases de gatilho, um caso de
caminho feliz por habilidade, um caso de desvio para a verificação de ocultação do doctor) — nunca
executada por `poe check`; o responsável a executa manualmente ou a partir do job noturno, por meio
de CLIs de assinatura, nunca a API medida. Veja o [próprio
README](../../packages/narrativetrace-skills/evals/README.md) para a política dos carris
esporádicos (Codex/Gemini) e a matriz de promoção.

## Veja também

- [`narrativetrace-skills`](../../packages/narrativetrace-skills/README.md) — o pacote do
  catálogo tipado
- [Sessenta segundos](sessenta-segundos.md) — o passo a passo de instalação e primeiro trace do
  qual os passos do `add-narrative-tracing` são extraídos
- [O que commitar](o-que-commitar.md) — o estado das traces de aprovação que o quarto passo do
  doctor verifica
