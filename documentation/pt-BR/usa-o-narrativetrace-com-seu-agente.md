<!-- source: documentation/use-with-your-agent.md blob d89822d53ce8 | translated: 2026-10-10 | reviewed: - -->

# Use o NarrativeTrace com o seu agente

O NarrativeTrace inclui [habilidades de agente](habilidades-do-agente.md) — os procedimentos que um
agente segue para instalar a biblioteca, ler um trace e diagnosticar uma instalação — no formato
aberto Agent Skills. Todas as plataformas da tabela abaixo já descobrem as páginas que o `init`
escreve em `.agents/skills`, então há um único conjunto de páginas e nenhuma cópia por plataforma. O
que muda de uma plataforma para outra é como alguém de fora leva as páginas para um projeto, e qual
pequeno arquivo aponta o agente para elas antes que ele pense em procurar.

## Plataformas num relance

<!-- platform-table:begin -->
| Plataforma | Como alguém de fora obtém as habilidades | O que o agente encontra depois do `init` | Evidência | Verificado |
|---|---|---|---|---|
| Cursor | Instale o plugin a partir do manifesto `.cursor-plugin` do repositório público, ou execute `uv run narrativetrace init` no projeto | as habilidades em `.agents/skills` (o Cursor também lê `.claude/skills`) e a regra `.cursor/rules/narrativetrace.mdc` que aponta para elas | faixa Tier B `cursor` | 2026-10-10 |
| Replit | Importe o repositório público do GitHub (cole a URL, pré-visualize as habilidades e adicione-as), ou execute `uv run narrativetrace init` no projeto | as habilidades em `.agents/skills` e uma seção do NarrativeTrace no `replit.md`, a memória do projeto que o agente do Replit lê primeiro | teste manual | 2026-10-10 |
| Antigravity | Nada a instalar além do próprio projeto: execute `uv run narrativetrace init` no projeto e faça commit das habilidades (a CLI `agy` e a IDE as leem como habilidades do workspace) | as habilidades em `.agents/skills`, que o Antigravity lê como habilidades do workspace, e a seção do `AGENTS.md`, que ele carrega como regras | faixa Tier B `antigravity` | 2026-10-10 |
| GitHub Copilot | Nada a instalar além do próprio repositório: execute `uv run narrativetrace init` no projeto e faça commit das habilidades | as habilidades em `.agents/skills` (o Copilot também lê `.claude/skills` e `.github/skills`) e a seção do `AGENTS.md` | teste manual | 2026-10-10 |
| Claude Code | Adicione o repositório como marketplace de plugins e instale o plugin dele, ou execute `uv run narrativetrace init` no projeto | as habilidades em `.claude/skills` e `.agents/skills`, e a seção do `AGENTS.md` que o `CLAUDE.md` importa | faixa Tier B `claude` | 2026-10-10 |
<!-- platform-table:end -->

A tabela é gerada a partir do registro de plataformas que o instalador e o doctor leem, então ela não
pode contradizer o que o `init` faz. A coluna Verificado é a data em que os fatos de cada linha foram
conferidos pela última vez com a documentação da própria plataforma; o comportamento das plataformas
muda depressa, então trate essa data como parte da resposta e a documentação do fornecedor como a
autoridade.

## Os arquivos de aviso que o `init` escreve

Um aviso é um pequeno arquivo que a plataforma já lê primeiro. Ele só é escrito quando o projeto
mostra que a plataforma está em uso, nunca como cópia de uma página de habilidade, e nunca através de
um link simbólico:

- **Cursor** — `.cursor/rules/narrativetrace.mdc`, uma regra sempre aplicada que diz onde estão as
  habilidades, escrita somente quando o projeto tem um diretório `.cursor/`. O plugin do Cursor traz a
  mesma regra.
- **Replit** — uma seção marcada do NarrativeTrace no `replit.md`, a memória do projeto que o agente
  do Replit lê primeiro, escrita somente quando o projeto tem `replit.md` ou `.replit`. É a mesma seção
  que o `AGENTS.md` carrega, com os mesmos marcadores.
- **Antigravity, GitHub Copilot, Claude Code** — sem aviso. Eles leem `.agents/skills` e `AGENTS.md`
  diretamente (o Antigravity carrega o `AGENTS.md` como regras; o Claude Code também lê
  `.claude/skills`, que o `init` escreve em todo projeto).

Um aviso que já é idêntico ao que o `init` escreveria é adotado em vez de recusado, um arquivo que não
é nosso é recusado sem `--force`, e `uv run narrativetrace uninstall` remove exatamente os avisos que
escreveu. `uv run narrativetrace doctor` informa o aviso de cada plataforma detectada como presente e
atual, ou nomeia o que está faltando, desatualizado ou que não é nosso.

## Copiando à mão

Copiar funciona para qualquer plataforma, e é o único caminho para um agente sem um comando
`narrativetrace` próprio:

- **Codex**: o catálogo renderiza
  [`.agents/skills/narrativetrace-doctor/`](../../.agents/skills/narrativetrace-doctor/SKILL.md) e os
  demais diretórios de habilidades da mesma pasta — o layout que o Codex CLI documenta para as
  habilidades próprias de um projeto. O frontmatter dele traz somente `name` e `description` (o Codex
  não documenta as chaves `when_to_use` nem `allowed-tools`); o corpo da página é idêntico. Copie o
  diretório relevante para o `.agents/skills/<nome>/` do seu próprio projeto e o Codex o descobre do
  mesmo modo.
- **Antigravity**: as habilidades do workspace são lidas de `.agents/skills/` (o antigo
  `.agent/skills/`), então a mesma cópia serve na IDE e na CLI `agy`. O instalador de plugins dele
  lê somente o diretório `skills/` de nível superior de um plugin, que este repositório não
  distribui, então não há um caminho `agy plugin install`.
- **Qualquer agente, qualquer plataforma**: todo agente que lê o `AGENTS.md` vê a seção sempre ativa
  que o `init` escreve ali — o nome e a descrição das habilidades, para que um agente que nunca pensou
  em procurá-las ainda assim saiba que existem.

## Evidência

A linha de cada plataforma nomeia o teste que a sustenta. As faixas do Claude, Codex, Antigravity e Cursor
executam o agente real de linha de comando contra o prompt de instalação em um projeto de exemplo, e
uma faixa cuja CLI não está instalada é pulada com uma única linha em vez de falhar; Replit e GitHub
Copilot são testes manuais registrados pelo proprietário. As faixas, a política esporádica de cotas e
a matriz de promoção estão descritas em
[Tier B — testes com LLM](../../packages/narrativetrace-skills-catalogue/evals/README.md).

## Relacionados

- [Habilidades do agente](habilidades-do-agente.md) — o que são as habilidades, como são construídas e o instalador
- [Guia de instalação](guia-de-instalacao.md) — a biblioteca em si
