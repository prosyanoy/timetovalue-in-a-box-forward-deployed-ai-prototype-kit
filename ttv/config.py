"""Environment-driven settings with safe local defaults (no secrets required)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    return float(raw) if raw.strip() else default


@dataclass(frozen=True)
class Settings:
    scenario: str = "network-anomaly"
    bus_url: str = "memory"  # "memory" or nats://host:4222
    subject: str = "ttv.events"
    seed: int = 7
    start_epoch: float | None = None  # when the stopwatch started (set by `make up`)
    event_rate: float = 5.0  # events/second from the generator
    anomaly_rate: float = 0.1
    embedded_generator: bool = False  # run the generator inside the model service (local demo)
    llm_base_url: str = ""  # optional OpenAI-compatible endpoint, e.g. http://localhost:11434/v1
    llm_model: str = "llama3.2"
    llm_api_key: str = ""
    llm_timeout: float = 4.0
    otel_endpoint: str = ""  # OTLP/HTTP base URL of the collector; empty disables export
    model_url: str = "http://localhost:8081"  # used by the dashboard

    @classmethod
    def from_env(cls) -> "Settings":
        start = os.environ.get("TTV_START_EPOCH", "").strip()
        return cls(
            scenario=os.environ.get("SCENARIO", cls.scenario),
            bus_url=os.environ.get("BUS_URL", cls.bus_url),
            subject=os.environ.get("BUS_SUBJECT", cls.subject),
            seed=int(_float("SEED", cls.seed)),
            start_epoch=float(start) if start else None,
            event_rate=_float("EVENT_RATE", cls.event_rate),
            anomaly_rate=_float("ANOMALY_RATE", cls.anomaly_rate),
            embedded_generator=os.environ.get("EMBEDDED_GENERATOR", "0") == "1",
            llm_base_url=os.environ.get("LLM_BASE_URL", ""),
            llm_model=os.environ.get("LLM_MODEL", cls.llm_model),
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            llm_timeout=_float("LLM_TIMEOUT", cls.llm_timeout),
            otel_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            model_url=os.environ.get("MODEL_URL", cls.model_url),
        )
