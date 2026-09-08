<!-- source: documentation/guides/opentelemetry.md blob 8c80d624163c | translated: 2026-09-03 | reviewed: 2026-09-03 -->

# OpenTelemetry

`narrativetrace-otel` emite sua narrativa como spans do OpenTelemetry — o trace humano e a
correlação de backend a partir de uma única captura. Depende apenas de `opentelemetry-api`.

## Exportação em lote (árvore completa)

```python
from opentelemetry import trace
from narrativetrace_otel import TraceSpanExporter

TraceSpanExporter(trace.get_tracer("orders")).export(context.capture_trace().roots)
```

Cada nó vira um span aninhado com atributos `narrative.class`/`narrative.method`, atributos
`narrative.param.<name>` tipados, `narrative.outcome`, `narrative.duration_ms`, atributos de
concorrência, e atributos de esquema `nt.*` em **todo** span.

## Streaming ao vivo (span por evento)

Anexe `OtelTraceEventListener` ao pipeline para abrir um span em cada entrada e fechá-lo na saída
correspondente, ancorado nos **timestamps do evento** (não no tempo de processamento). Spans órfãos
(entrada sem saída) são despejados por um `PerishableMap` limitado e encerrados com status de erro.

```python
from narrativetrace_otel import OtelTraceEventListener

listener = OtelTraceEventListener(trace.get_tracer("orders"))
# alimente-o com TraceEvents vindos do pipeline de captura
```

## Vocabulário de atributos

Chaves de nível de trace (somente spans raiz): `narrative.service.name/version/environment`,
`narrative.http.method/route`, `narrative.client_ip`, `narrative.enduser.id`,
`narrative.session.id`, `narrative.tenant.id`. Identidade + `nt.entryType`/`nt.schemaVersion`
aparecem em todo span, então qualquer span é correlacionável de forma independente.
