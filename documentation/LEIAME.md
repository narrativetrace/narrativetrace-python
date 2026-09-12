# Documentação do NarrativeTrace

[English](README.md) | [Español](LEAME.md) | **Português** | [简体中文](自述文件.md)

O índice dos documentos de usuário deste repositório, em português. Cada documento aqui listado
é uma tradução derivada da sua fonte em inglês — veja [`i18n/manifest.json`](i18n/manifest.json)
para o conjunto de idiomas declarado e o status de cada tradução. Documentos apenas de engenharia
(registros de ADR, notas de testes de segurança/concorrência, notas de design datadas) são somente
em inglês por convenção e não fazem parte do conjunto traduzido de nenhum idioma — consulte o
[índice em inglês](README.md) para vê-los.

## Comece aqui

| Documento | O que cobre |
|---|---|
| [Veja um trace em 60 segundos](pt-BR/sessenta-segundos.md) | Um serviço minúsculo, saída real, da instalação a um valor ocultado |
| [Escolhendo uma integração](pt-BR/escolhendo-uma-integracao.md) | Qual pacote você precisa, como diagrama de decisão |
| [Guia de instalação](pt-BR/guia-de-instalacao.md) | Cada pacote, o que ele adiciona |
| [Guia de configuração](pt-BR/guia-de-configuracao.md) | Níveis de tracing, configurações de saída, cadeia de precedência |
| [Guia de decoradores](pt-BR/guia-de-decoradores.md) | `@narrated`, `@on_error`, `@not_traced`, o contrato de pureza |
| [Privacidade e ocultação](pt-BR/privacidade-e-ocultacao.md) | O contrato de ocultação linha por linha, verificado contra o código |
| [O que commitar](pt-BR/o-que-commitar.md) | Quais arquivos gerados são artefatos de CI, e quais (se algum) são baselines revisadas |
| [Formato de trace estrutural](pt-BR/formato-de-trace-estrutural.md) | O artefato `.nt` livre de valores: gramática, nomeação por invocação, baseline verde, modo de aprovação |
| [Solução de problemas](pt-BR/solucao-de-problemas.md) | Sintoma → causa → correção para os modos de falha que as pessoas realmente encontram |

## Integrações

| Documento | O que cobre |
|---|---|
| [Guia de pytest](pt-BR/guia-de-pytest.md) | A fixture `narrative_trace`, artefatos por teste, o rodapé de clareza |
| [Guia de FastAPI / ASGI](pt-BR/guia-de-fastapi-asgi.md) | Middleware do Starlette/FastAPI, traceparent W3C, o acessor de requisição |
| [Guia de OpenTelemetry](pt-BR/guia-de-opentelemetry.md) | A ponte de spans do OTel: listener ao vivo e exportador em lote |
| [Guia de logging](pt-BR/guia-de-logging.md) | A ponte de logging da stdlib e o processador de structlog |

## Análise e saída

| Documento | O que cobre |
|---|---|
| [Guia de clareza](pt-BR/guia-de-clareza.md) | O modelo de pontuação, a integração equivalente ao JUnit, e o gate estilo `clarityCheck` |
| [Guia de funcionalidades](pt-BR/guia-de-funcionalidades.md) | O catálogo canônico: cada funcionalidade, seu nível, seu status |

## Mantendo este índice honesto

Adicionar ou remover uma tradução sob `documentation/pt-BR/` significa atualizar este arquivo e
`documentation/i18n/manifest.json` na mesma mudança. Um documento que não aparece aqui é invisível
para quem navega o repositório em português.
