"""Local trace export is opt-in; no external telemetry endpoint is contacted."""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from .config import settings


def redact_request_target(span, scope):
    """Search text and future URL secrets must not enter automatic HTTP spans."""
    if span and span.is_recording():
        path = scope.get('path', '/')
        for name in ('http.url', 'http.target', 'url.full', 'url.path'):
            span.set_attribute(name, path)
        span.set_attribute('url.query', '')


def configure_tracing():
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return
    provider = TracerProvider()
    if settings().otel_console:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
