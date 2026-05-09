"""
OpenTelemetry configuration for Presek

This module provides centralized tracing setup for distributed tracing
across the Presek application services.

Usage:
    from opentelemetry_config import setup_tracing, get_tracer
    
    # At application startup
    setup_tracing(service_name="presek-api")
    
    # In modules
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("my-operation"):
        # ... do work ...
"""

import os
from typing import Optional
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as HTTPOTLPSpanExporter
from opentelemetry.trace import Status, StatusCode


# Global tracer provider
_tracer_provider: Optional[TracerProvider] = None


def setup_tracing(
    service_name: str = "presek",
    service_version: str = "0.1.0",
    environment: str = "development",
    otlp_endpoint: Optional[str] = None,
    otlp_insecure: bool = False,
) -> TracerProvider:
    """
    Configure OpenTelemetry tracing for the application.
    
    Args:
        service_name: Name of the service (e.g., 'presek-api', 'presek-worker')
        service_version: Version of the service
        environment: Deployment environment (development, staging, production)
        otlp_endpoint: OTLP collector endpoint (e.g., 'localhost:4317')
        otlp_insecure: Whether to use insecure connection to OTLP endpoint
    
    Returns:
        Configured TracerProvider
    """
    global _tracer_provider
    
    # Determine configuration from environment
    env = os.environ.get("ENV", environment)
    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    insecure = otlp_insecure or os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "").lower() == "true"
    
    # Create resource with service metadata
    resource = Resource.create({
        "service.name": service_name,
        "service.version": service_version,
        "deployment.environment": env,
    })
    
    # Create tracer provider
    _tracer_provider = TracerProvider(resource=resource)
    
    # Configure span processors
    span_processors = [
        # Always log spans to console in development
        BatchSpanProcessor(ConsoleSpanExporter()) if env != "production" else None,
    ]
    
    # Add OTLP exporter if endpoint is configured
    if endpoint:
        try:
            if endpoint.startswith("http://") or endpoint.startswith("https://"):
                otlp_exporter = HTTPOTLPSpanExporter(
                    endpoint=endpoint,
                    insecure=insecure,
                )
            else:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=endpoint,
                    insecure=insecure,
                )
            span_processors.append(BatchSpanProcessor(otlp_exporter))
        except Exception as e:
            # Log but don't fail if OTLP setup fails
            import logging
            logging.getLogger("presek.opentelemetry").warning(
                f"Failed to configure OTLP exporter: {e}"
            )
    
    # Filter out None processors
    span_processors = [p for p in span_processors if p is not None]
    
    if span_processors:
        _tracer_provider.add_span_processor(
            BatchSpanProcessor(*span_processors) if len(span_processors) > 1 else span_processors[0]
        )
    
    # Set as global tracer provider
    trace.set_tracer_provider(_tracer_provider)
    
    # Auto-instrument common libraries
    _setup_auto_instrumentation()
    
    return _tracer_provider


def _setup_auto_instrumentation():
    """Configure auto-instrumentation for common libraries."""
    # Auto-instrumentation is optional and can be added manually
    # Try to import and instrument common libraries
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app()
    except ImportError:
        pass
    
    try:
        from opentelemetry.instrumentation.httpx import HTTPXInstrumentor
        HTTPXInstrumentor.instrument()
    except ImportError:
        pass
    
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor.instrument()
    except ImportError:
        pass
    
    try:
        from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
        Psycopg2Instrumentor.instrument()
    except ImportError:
        pass
    
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        CeleryInstrumentor.instrument()
    except ImportError:
        pass


def get_tracer(name: str) -> trace.Tracer:
    """
    Get a tracer for the given module/package name.
    
    Args:
        name: Module/package name (typically __name__)
    
    Returns:
        Tracer instance
    """
    if _tracer_provider is None:
        setup_tracing()
    return trace.get_tracer(name)


def create_span(
    name: str,
    tracer_name: Optional[str] = None,
    **attributes,
):
    """
    Convenience function to create a span with attributes.
    
    Args:
        name: Span name
        tracer_name: Tracer name (defaults to caller's module)
        **attributes: Additional span attributes
    
    Returns:
        Context manager for the span
    """
    import inspect
    from contextlib import contextmanager
    
    if tracer_name is None:
        # Get caller's module name
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back.f_back
            tracer_name = inspect.getmodule(caller_frame).__name__
        finally:
            del frame
    
    tracer = get_tracer(tracer_name)
    
    @contextmanager
    def span_context():
        with tracer.start_as_current_span(name, attributes=attributes) as span:
            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, description=str(e)))
                raise
    
    return span_context()


# Auto-setup on import if enabled
if os.environ.get("OTEL_ENABLED", "").lower() == "true":
    import logging
    log = logging.getLogger("presek.opentelemetry")
    service_name = os.environ.get("OTEL_SERVICE_NAME", "presek")
    log.info(f"Auto-configuring OpenTelemetry for service: {service_name}")
    setup_tracing(service_name=service_name)
