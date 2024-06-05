"""Live pipeline measurements: confusion counts, detection latency and the time-to-first-insight stopwatch."""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Metrics:
    start_epoch: float | None = None
    processed: int = 0
    alerts: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    first_event_at: float | None = None
    first_insight_at: float | None = None
    latencies: list[float] = field(default_factory=list)  # event emit -> insight, true detections only
    recent: deque = field(default_factory=lambda: deque(maxlen=50))
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, insight: dict, label: int | None, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        with self._lock:
            self.processed += 1
            if self.first_event_at is None:
                self.first_event_at = now
            alert = insight["alert"]
            if alert:
                self.alerts += 1
                self.recent.appendleft(insight)
                if self.first_insight_at is None:
                    self.first_insight_at = now
            if label is not None:
                if alert and label:
                    self.tp += 1
                    self.latencies.append(max(insight["latency_s"], 0.0))
                elif alert:
                    self.fp += 1
                elif label:
                    self.fn += 1
                else:
                    self.tn += 1

    def snapshot(self) -> dict:
        with self._lock:
            tp, fp, fn, tn = self.tp, self.fp, self.fn, self.tn
            lat = np.array(self.latencies) if self.latencies else None
            ttv = None
            if self.start_epoch is not None and self.first_insight_at is not None:
                ttv = round(self.first_insight_at - self.start_epoch, 3)
            return {
                "processed": self.processed,
                "alerts": self.alerts,
                "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
                "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None,
                "false_positive_rate": fp / (fp + tn) if fp + tn else None,
                "false_positive_share": fp / (tp + fp) if tp + fp else None,
                "detection_latency_s": {
                    "mean": float(lat.mean()) if lat is not None else None,
                    "p95": float(np.percentile(lat, 95)) if lat is not None else None,
                },
                "start_epoch": self.start_epoch,
                "first_insight_at": self.first_insight_at,
                "time_to_first_insight_s": ttv,
            }

    def recent_insights(self, limit: int = 20) -> list[dict]:
        with self._lock:
            return list(self.recent)[:limit]
