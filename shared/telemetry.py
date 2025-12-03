import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

logger = logging.getLogger(__name__)


def setup_telemetry(service_name: str, service_version: str = "1.0.0"):
    """
    Initialize OpenTelemetry with OTLP exporter.
    
    Environment variables:
        OTEL_EXPORTER_OTLP_ENDPOINT: Collector endpoint (default: http://otel-collector:4317)
        OTEL_SERVICE_NAME: Override service name
        DEPLOYMENT_ENV: Environment name (default: production)
        OTEL_ENABLED: Set to "false" to disable (default: true)
    """
    if os.getenv("OTEL_ENABLED", "true").lower() == "false":
        logger.info("OpenTelemetry disabled via OTEL_ENABLED=false")
        return None
    
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    env_name = os.getenv("DEPLOYMENT_ENV", "production")
    
    resource = Resource.create({
        SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", service_name),
        SERVICE_VERSION: service_version,
        DEPLOYMENT_ENVIRONMENT: env_name,
        "service.namespace": "lottery-system",
    })
    
    provider = TracerProvider(resource=resource)
    
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(provider)
        
        # Auto-instrument common libraries
        HTTPXClientInstrumentor().instrument()
        RedisInstrumentor().instrument()
        LoggingInstrumentor().instrument(set_logging_format=True)
        
        logger.info(f"OpenTelemetry initialized for {service_name}, exporting to {endpoint}")
        return provider
        
    except Exception as e:
        logger.warning(f"Failed to initialize OpenTelemetry: {e}")
        return None


def instrument_fastapi(app):
    """Instrument a FastAPI application."""
    try:
        FastAPIInstrumentor.instrument_app(app)
    except Exception as e:
        logger.warning(f"Failed to instrument FastAPI: {e}")


def get_tracer(name: str):
    """Get a tracer for manual instrumentation."""
    return trace.get_tracer(name)

