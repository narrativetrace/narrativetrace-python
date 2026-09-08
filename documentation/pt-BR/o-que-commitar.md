<!-- source: documentation/what-to-commit.md blob ab4d416d0d4f | translated: 2026-09-07 | reviewed: - -->

# O que commitar

Tudo o que o NarrativeTrace grava hoje é um **artefato gerado que descreve uma execução** — ainda não
existe nesta implementação um arquivo de baseline revisada (o formato estrutural `.nt` da implementação Java e
seu fluxo de approval testing estão planejados aqui, mas ainda não lançados — veja o
[Guia de funcionalidades](guia-de-funcionalidades.md)). Até isso chegar, a regra é simples: nada sob
o seu diretório de saída configurado é código-fonte, então nada disso pertence ao controle de versão.

| Artefato | Padrão de caminho | Commitar? | Por quê |
|---|---|---|---|
| Arquivo de trace (Markdown, formato padrão) | `<OUTPUT_DIR>/traces/<Class>/<slug>.md` | Não | Regenerado a cada execução |
| Arquivo de trace (formato `text`/`mermaid`/`plantuml`) | `<OUTPUT_DIR>/traces/<Class>/<slug>.{txt,mmd,puml}` | Não | Regenerado a cada execução |
| Documento de cenário JSON (apenas formato Markdown) | `<OUTPUT_DIR>/traces/<Class>/<slug>.json` | Não | O mesmo trace como JSON canônico — regenerado a cada execução |
| Diagrama Mermaid complementar (apenas formato Markdown) | `<OUTPUT_DIR>/diagrams/<Class>/<slug>.mmd` | Não | Regenerado a cada execução |
| Array de entradas canônico | `<OUTPUT_DIR>/traces/<Class>/<slug>.canonical.json` | Não | Um artefato para máquinas, usado em conformidade/portes, opt-in via `NARRATIVETRACE_CANONICAL` |
| Relatório de clareza da suíte | `<OUTPUT_DIR>/clarity-report.md` | Não | Um relatório gerado, não uma decisão |
| Resultados de clareza da suíte | `<OUTPUT_DIR>/clarity-results.json` | Não | Gerado junto com o relatório |
| Saída do scanner independente (CLI `narrativetrace-clarity`) | onde `--output-dir` apontar | Não | Igual ao anterior, gerado sob demanda |
| `glossary.json` / `glossary.md` | raiz do repositório (ou onde você apontar `NARRATIVETRACE_GLOSSARY_DIR`) | **Sim**, se você o usa | Vocabulário de propriedade humana — o arquivo commitado é o que a pontuação de clareza lê de volta, e nunca é regenerado por uma execução de testes. "Um arquivo, um fluxo de revisão" |

O `<OUTPUT_DIR>` padrão é `narrative-traces` (relativo a onde a suíte rodou); adicione-o ao
`.gitignore` do seu projeto:

```gitignore
narrative-traces/
```

Se você apontar `NARRATIVETRACE_OUTPUT_DIR` para outro lugar — um diretório `build/`, uma pasta de
artefatos de CI —, ignore esse caminho em vez disso. `glossary.json` é a única exceção: ele vive onde
você o colocar (tipicamente a raiz do repositório), nunca é gravado por uma execução de testes, e
deve ser versionado como qualquer outro arquivo-fonte.

## A regra em uma frase

Se um arquivo só existe porque um teste rodou, ele é saída — não commite. `glossary.json` é o único
arquivo nesta lista que um humano escreve e que uma execução apenas *lê* — é isso que faz dele a
única exceção.

## O que muda quando o approval testing chegar

Os arquivos `.approved.nt` / `.received.nt` da implementação Java são uma categoria genuinamente
diferente — uma baseline estrutural revisada por um humano é uma decisão, não uma saída, e pertence
ao controle de versão da mesma forma que o golden file de um snapshot test. Esta implementação ainda não tem
esse mecanismo; quando tiver, esta página ganhará a mesma divisão em duas categorias que o Java
documenta (baseline revisada: commitar; tudo o mais: não) em vez de uma reescrita do zero.
