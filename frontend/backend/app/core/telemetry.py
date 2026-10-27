from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import settings


def configure_telemetry(app: FastAPI) -> None:
    endpoint = settings.otel_exporter_otlp_endpoint
    if endpoint:
        provider = TracerProvider(resource=Resource.create({"service.name": "fleet-studio-api"}))
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=endpoint, headers=settings.otel_exporter_otlp_headers or None)
            )
        )
        trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)