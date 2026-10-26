"""OpenTelemetry tracing (spec 14.2). Enabled only when an OTLP endpoint is
configured; otherwise spans are no-ops so local development needs no collector.
Span attributes carry safe identifiers only — never prompt content or secrets."""

from __future__ import annotations

import contextlib

from ..config import get_settings

_tracer = None


def setup_tracing(app=None) -> None:
    global _tracer
    settings = get_settings()
    if not settings.otel_endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "modelrail-gateway"}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint)))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("modelrail")
        if app is not None:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
    except Exception:
        _tracer = None


@contextlib.contextmanager
def span(name: str, **attributes):
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current
