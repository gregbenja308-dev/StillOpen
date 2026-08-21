"""OpenTelemetry spans. Console locally; Cloud Trace in cloud."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from stillopen_core.config import OtelExporter, get_settings

_started = False


def setup_tracing() -> None:
    """Install a TracerProvider once. No-op if exporter is none or SDK missing."""
    global _started
    if _started:
        return
    _started = True
    settings = get_settings()
    if settings.otel_exporter is OtelExporter.NONE:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
    except ImportError:
        return

    resource = Resource.create({"service.name": settings.service_name})
    provider = TracerProvider(resource=resource)
    if settings.otel_exporter is OtelExporter.GCP and settings.gcp_project:
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(
                    CloudTraceSpanExporter(project_id=settings.gcp_project)  # type: ignore[no-untyped-call]
                )
            )
        except ImportError:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)


def current_trace_id() -> str | None:
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")


@contextmanager
def start_span(name: str, **attrs: Any) -> Iterator[Any]:
    """Current-span context. No-op tracer if setup_tracing was never called."""
    try:
        from opentelemetry import trace
    except ImportError:
        yield None
        return
    tracer = trace.get_tracer("stillopen")
    with tracer.start_as_current_span(name) as span:
        for key, value in attrs.items():
            if value is None:
                continue
            if isinstance(value, (bool, int, float, str)):
                span.set_attribute(key, value)
            else:
                span.set_attribute(key, str(value)[:200])
        yield span


__all__ = ["current_trace_id", "setup_tracing", "start_span"]
