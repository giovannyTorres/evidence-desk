"""Local trace export is opt-in; no external telemetry endpoint is contacted."""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from .config import settings


def configure_tracing():
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return
    provider = TracerProvider()
    if settings().otel_console:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
