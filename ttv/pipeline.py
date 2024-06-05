"""Event -> score -> summary. The transport-agnostic core of the model service."""
from __future__ import annotations

import time
import uuid

from .metrics import Metrics
from .scenarios import Scenario
from .scoring import AnomalyScorer
from .summarizer import Summarizer, diagnose, severity


class Pipeline:
    def __init__(self, scenario: Scenario, scorer: AnomalyScorer, summarizer: Summarizer, metrics: Metrics):
        self.scenario = scenario
        self.scorer = scorer
        self.summarizer = summarizer
        self.metrics = metrics

    def validate(self, event: dict) -> dict[str, float]:
        features = event.get("features")
        if not isinstance(features, dict):
            raise ValueError("event.features must be an object")
        missing = [k for k in self.scenario.feature_keys if k not in features]
        if missing:
            raise ValueError(f"missing features: {', '.join(missing)}")
        return {k: float(features[k]) for k in self.scenario.feature_keys}

    def process(self, event: dict, now: float | None = None) -> dict:
        values = self.validate(event)
        now = now if now is not None else time.time()
        score, alert = self.scorer.score(values)
        entity = str(event.get("entity", "unknown"))
        insight = {
            "id": str(event.get("id") or uuid.uuid4()),
            "scenario": self.scenario.name,
            "entity": entity,
            "ts": float(event.get("ts", now)),
            "scored_at": now,
            "latency_s": now - float(event.get("ts", now)),
            "score": round(score, 4),
            "threshold": round(self.scorer.threshold, 4),
            "alert": alert,
            "severity": None,
            "kind": None,
            "summary": None,
            "summary_source": None,
            "features": values,
        }
        if alert:
            sev = severity(self.scenario, values)
            kind = diagnose(self.scenario, values)
            summary, source = self.summarizer.summarize(entity, values, sev, kind)
            insight.update(severity=sev, kind=kind, summary=summary, summary_source=source)
        label = event.get("label")
        self.metrics.record(insight, None if label is None else int(label), now=time.time())
        return insight
