<!-- source: documentation/guides/clarity.md blob 27a21b6573d8 | translated: 2026-09-07 | reviewed: - -->

# Clareza

Como o trace *é* os seus nomes, `narrativetrace-clarity` pontua a qualidade dos nomes de forma
objetiva e pode fazer a CI falhar quando os nomes se degradam.

## Pontuando um trace

```python
from narrativetrace_clarity import analyze

result = analyze(context.capture_trace())
print(result.overall_score)          # 0.0 (ruim) … 1.0 (excelente)
for issue in result.issues:          # ordenados por impacto
    print(issue.severity.name, issue.category, issue.element, "→", issue.suggestion)
```

Cinco dimensões ponderadas: nomes de método (0.30), nomes de classe (0.20), nomes de parâmetro
(0.25), estrutural (0.15), coesão (0.10). As pontuações usam dicionários idênticos byte a byte
compartilhados entre os runtimes do NarrativeTrace: 1053 verbos em 34 categorias de domínio, 187 abreviações, 35 mapas de colocação e
sufixos de papel.

Os problemas são classificados por faixa de pontuação (HIGH ≤ 0.20, MEDIUM ≤ 0.50), deduplicados por
`category|element` com ocorrências somadas, e ordenados por impacto.

## Seu próprio vocabulário, a partir do glossário que você já tem

Os dicionários embutidos conhecem o inglês geral de software. Eles não sabem que `fold` é um verbo
no seu domínio, que `tranche` é um substantivo preciso, ou que `fx` é uma abreviação que sua equipe
aceitou — e um nome que eles não conhecem pontua como desconhecido, não como específico de domínio.

Você os ensina com o arquivo de vocabulário que seu repositório já tem: o `glossary.json` commitado
(ADR-012). Não há um segundo arquivo de dicionário para manter sincronizado.

| Entrada do glossário | Tipo | O que a clareza aprende |
|---|---|---|
| `settle trade` | `verb-phrase` | `settle` é um verbo de domínio; `trade` é um substantivo de domínio |
| `credit tranche` | `noun-phrase` | `credit` e `tranche` são substantivos de domínio |
| `fx` | `word` | `fx` é um substantivo de domínio |

Termos com várias palavras ensinam um token por vez, porque identificadores são pontuados um token
por vez. Todo contexto delimitado contribui: um identificador não carrega um caminho de módulo,
então o escopo por contexto não pode ser aplicado no momento da pontuação.

### Abreviação aceita é sua própria seção

Quais abreviações seu projeto aceita é uma decisão independente de quais palavras seu domínio usa,
então isso vive em sua própria seção de nível raiz do `glossary.json` (esquema 2):

```json
{
  "schemaVersion": 2,
  "contexts": { "trading": { "packages": ["acme.trading"] } },
  "abbreviations": { "fx": "foreign exchange", "calc": "calculate" },
  "terms": []
}
```

Um token listado ali nunca é solicitado a ser escrito por extenso. Um token que apenas *aparece
dentro de* um termo commitado não é: commitar a frase nominal `calc total` ensina que `calc` e
`total` são substantivos de domínio, e não diz nada sobre se `calc` é uma abreviação aceita — então a
dica `calc` → `calculate` sobrevive para o resto do repositório.

A seção é de propriedade humana: a coleta nunca a escreve, e mesclar uma coleta a mantém intacta. Um
glossário que não declara nenhuma fica marcado com `"schemaVersion": 1` e grava exatamente os mesmos
bytes que gravava antes de a seção existir, então adotar a funcionalidade não gera ruído no diff.
Leitores aceitam a seção em qualquer versão de esquema.

Os dicionários embutidos mantêm sua autoridade. Um projeto pode ensinar aos avaliadores uma palavra
que eles não conhecem; não pode anular uma que eles conhecem — verbos genéricos (`process`,
`handle`) e prefixos booleanos (`is`, `has`) ficam onde estão, marcadores sem significado (`temp`,
`foo`) não são resgatados por estarem escritos, e sinônimos obsoletos, entradas `template` e termos
`stale` nunca são vocabulário. Só conta o arquivo *commitado*: nada que uma execução coleta
realimenta as pontuações dessa mesma execução, o que as tornaria não determinísticas e
autocertificadas.

```python
from narrativetrace_clarity import analyze
from narrativetrace_glossary import read_project_vocabulary

result = analyze(context.capture_trace(), read_project_vocabulary("."))
```

O plugin do pytest faz isso por você, uma vez por sessão: `narrativetrace.glossary_dir` (env
`NARRATIVETRACE_GLOSSARY_DIR`) nomeia o diretório, com o diretório de trabalho como padrão. A leitura
é incondicional — não muda nada em disco — e um glossário que não pode ser lido degrada para os
dicionários embutidos com um aviso em vez de falhar a suíte.

## O gate de CI

O script de console `narrativetrace-clarity` escaneia fontes Python (cada método público é uma raiz
de profundidade 1) e grava `clarity-results.json` + `clarity-report.md`:

```bash
narrativetrace-clarity src --min-score 0.5 --max-high-issues 0 --output-dir build/narrativetrace
# --format both|md|json   --warn-only   (formato desconhecido → saída 2; abaixo do limiar → saída 1)
```

Neste repositório está conectado ao `uv run poe check` via a task `clarity`.

## Agregação em tempo de execução

O plugin do pytest pontua a árvore capturada de cada teste, imprime um rodapé
`Clarity: X% high | …`, e (com a saída habilitada) agrega uma entrada de `clarity-results.json` por
teste traçado.
