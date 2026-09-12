<!-- source: documentation/what-to-commit.md blob 932b2f208abd | translated: 2026-09-12 | reviewed: - -->

# O que commitar

Duas categorias, não uma. Quase tudo o que o NarrativeTrace grava é um **artefato gerado que
descreve uma execução** — nada sob o seu diretório de saída configurado é código-fonte, então nada
disso pertence ao controle de versão. A única exceção é o **trace aprovado** (`.approved.nt`)
*(since 0.1.2, unreleased)*: um humano o revisou e o aceitou como o contrato de comportamento, da
mesma forma que o golden file de um snapshot test é uma decisão, não uma saída — veja a página
[Formato de trace estrutural](formato-de-trace-estrutural.md) para a gramática completa e o fluxo
de trabalho do modo de aprovação.

| Artefato | Padrão de caminho | Commitar? | Por quê |
|---|---|---|---|
| Arquivo de trace (Markdown, formato padrão) | `<OUTPUT_DIR>/traces/<Class>/<slug>.md` | Não | Regenerado a cada execução |
| Arquivo de trace (formato `text`/`mermaid`/`plantuml`) | `<OUTPUT_DIR>/traces/<Class>/<slug>.{txt,mmd,puml}` | Não | Regenerado a cada execução |
| Documento de cenário JSON (apenas formato Markdown) | `<OUTPUT_DIR>/traces/<Class>/<slug>.json` | Não | O mesmo trace como JSON canônico — regenerado a cada execução |
| Diagrama Mermaid complementar (apenas formato Markdown) | `<OUTPUT_DIR>/diagrams/<Class>/<slug>.mmd` | Não | Regenerado a cada execução |
| Array de entradas canônico | `<OUTPUT_DIR>/traces/<Class>/<slug>.canonical.json` | Não | Um artefato para máquinas, usado em conformidade/portes, opt-in via `NARRATIVETRACE_CANONICAL` |
| Trace estrutural (`.nt`, a última baseline verde) *(since 0.1.2, unreleased)* | `<OUTPUT_DIR>/structural/<Class>/<slug>.nt` | Não | Regenerado a cada execução verde — a cópia de trabalho *local*, não a baseline revisada abaixo |
| **Trace aprovado** *(since 0.1.2, unreleased)* | `<APPROVED_DIR>/<Class>/<slug>.approved.nt` | **Sim**, uma vez que você opte pelo modo de aprovação | O contrato de comportamento revisado — uma decisão, não uma saída |
| Trace recebido *(since 0.1.2, unreleased)* | `<APPROVED_DIR>/<Class>/<slug>.received.nt` | Não | Gravado em uma divergência (ou quando ainda não há baseline) para revisão; promova com `uv run poe approve` / `narrativetrace-approve`, nunca commite |
| Trace incompleto *(since 0.1.2, unreleased)* | `<APPROVED_DIR>/<Class>/<slug>.incomplete.nt` | Não | Gravado no lugar de um trace recebido quando a própria execução foi incompleta; o verbo approve o ignora pelo nome |
| `manifest.json` *(since 0.1.2, unreleased)* | `<OUTPUT_DIR>/manifest.json` | Não | Regenerado a cada execução — um índice sobre os artefatos acima, não uma baseline em si |
| Relatório de clareza da suíte | `<OUTPUT_DIR>/clarity-report.md` | Não | Um relatório gerado, não uma decisão |
| Resultados de clareza da suíte | `<OUTPUT_DIR>/clarity-results.json` | Não | Gerado junto com o relatório |
| Saída do scanner independente (CLI `narrativetrace-clarity`) | onde `--output-dir` apontar | Não | Igual ao anterior, gerado sob demanda |
| `glossary.json` / `glossary.md` | raiz do repositório (ou onde você apontar `NARRATIVETRACE_GLOSSARY_DIR`) | **Sim**, se você o usa | Vocabulário de propriedade humana — o arquivo commitado é o que a pontuação de clareza lê de volta, e nunca é regenerado por uma execução de testes. "Um arquivo, um fluxo de revisão" |

O `<OUTPUT_DIR>` padrão é `narrative-traces` e o `<APPROVED_DIR>` padrão é `test-narratives`
(ambos relativos a onde a suíte rodou, ambos configuráveis — veja o
[Guia de configuração](guia-de-configuracao.md)); ignore o diretório de saída e os dois padrões de
trace não aprovado sob o diretório de aprovação:

```gitignore
narrative-traces/
test-narratives/**/*.received.nt
test-narratives/**/*.incomplete.nt
```

Se você apontar `NARRATIVETRACE_OUTPUT_DIR`/`NARRATIVETRACE_APPROVED_DIR` para outro lugar — um
diretório `build/`, uma pasta de artefatos de CI —, ignore esses caminhos em vez disso.
`glossary.json` e um trace aprovado são as duas exceções nesta lista: arquivos que um humano
escreve (ou revisa e aceita) e que uma execução apenas *lê*, nunca sobrescreve — é isso que os
torna código-fonte.

## A regra em uma frase

Se um arquivo só existe porque um teste rodou, ele é saída — não commite. Se um arquivo existe
porque um humano o revisou e o aceitou, ele é uma baseline — commite. `glossary.json` e
`.approved.nt` são as únicas duas linhas nesta lista que um humano escreve ou aceita; tudo o mais é
regenerado.

## O modo de aprovação, visualmente

```text
o teste passa
   |
   v
compara a estrutura atual com o trace aprovado
   |
   +-- igual     --> passa, nada é gravado
   +-- diferente --> grava um trace recebido e falha
                     |
                     v
                um humano revisa o diff
                     |
                     v
              uv run poe approve  (ou narrativetrace-approve)
                     |
                     v
              .approved.nt atualizado, commite-o
```

`.approved.nt` nunca contém valores de parâmetro ou retorno — veja o
[Formato de trace estrutural](formato-de-trace-estrutural.md) para a gramática completa.
