"""OpenTelemetry wiring. Exports to the collector over OTLP/HTTP when an endpoint is configured."""
from __future__ import annotations

from typing import Callable

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class Telemetry:
    """Holds instruments; harmless no-ops when no collector endpoint is set."""

    def __init__(self, service: str, endpoint: str = "", ttv_getter: Callable[[], float | None] = lambda: None):
        resource = Resource.create({"service.name": service})
        readers, self._tracer_provider = [], TracerProvider(resource=resource)
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            base = endpoint.rstrip("/")
            self._tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(f"{base}/v1/traces")))
            readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(f"{base}/v1/metrics"),
                                                         export_interval_millis=5000))
        self._meter_provider = MeterProvider(resource=resource, metric_readers=readers)
        # private providers (not the global ones) so tests/apps can be created repeatedly
        self.tracer = self._tracer_provider.get_tracer("ttv")
        meter = self._meter_provider.get_meter("ttv")
        self.events = meter.create_counter("ttv.events.processed", description="events scored")
        self.alerts = meter.create_counter("ttv.alerts", description="anomalies flagged")
        self.latency = meter.create_histogram("ttv.pipeline.latency", unit="s", description="emit-to-insight latency")
        meter.create_observable_gauge(
            "ttv.time_to_first_insight", unit="s",
            callbacks=[lambda _o: [metrics.Observation(v)] if (v := ttv_getter()) is not None else []],
            description="seconds from `make up` to the first insight",
        )

    def observe(self, insight: dict) -> None:
        attrs = {"scenario": insight["scenario"]}
        self.events.add(1, attrs)
        self.latency.record(max(insight["latency_s"], 0.0), attrs)
        if insight["alert"]:
            self.alerts.add(1, {**attrs, "severity": insight["severity"], "kind": insight["kind"] or "unknown"})

    def shutdown(self) -> None:
        self._meter_provider.shutdown()
        self._tracer_provider.shutdown()


__all__ = ["Telemetry", "trace"]
