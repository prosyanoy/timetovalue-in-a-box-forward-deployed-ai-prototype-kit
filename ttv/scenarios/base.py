"""Scenario-pack contract: features, synthetic data generators, playbooks and ROI defaults."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Feature:
    key: str
    label: str  # plain-English name used in summaries
    unit: str
    mean: float
    std: float
    minimum: float = 0.0


@dataclass(frozen=True)
class Fault:
    """An anomaly archetype: which features shift (in baseline std-devs) and what to do about it."""

    kind: str
    title: str
    shifts: dict[str, float]
    action: str


@dataclass(frozen=True)
class RoiDefaults:
    """Customer-side assumptions for the ROI calculator (all overridable)."""

    anomalies_per_month: float
    baseline_detect_minutes: float  # how long the customer takes to notice today
    baseline_alerts_per_month: float  # alerts analysts review today
    baseline_fp_share: float  # share of today's alerts that are false
    triage_minutes_per_alert: float
    analyst_hourly_cost: float
    incident_cost_per_hour: float  # cost of every hour an anomaly goes undetected
    currency: str = "USD"


@dataclass(frozen=True)
class Scenario:
    name: str
    title: str
    description: str
    entity_noun: str  # "host", "machine"
    entities: tuple[str, ...]
    features: tuple[Feature, ...]
    faults: tuple[Fault, ...]
    roi: RoiDefaults
    _index: dict[str, Feature] = field(init=False, repr=False, compare=False, default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_index", {f.key: f for f in self.features})

    @property
    def feature_keys(self) -> list[str]:
        return [f.key for f in self.features]

    def feature(self, key: str) -> Feature:
        return self._index[key]

    def fault(self, kind: str) -> Fault:
        return next(f for f in self.faults if f.kind == kind)

    # -- synthetic data -------------------------------------------------
    def sample_normal(self, rng: np.random.Generator, n: int) -> np.ndarray:
        cols = [
            np.maximum(rng.normal(f.mean, f.std, n), f.minimum) for f in self.features
        ]
        return np.column_stack(cols)

    def sample_fault(self, rng: np.random.Generator, kind: str) -> dict[str, float]:
        fault = self.fault(kind)
        row = self.sample_normal(rng, 1)[0]
        out: dict[str, float] = {}
        for value, f in zip(row, self.features):
            shift = fault.shifts.get(f.key)
            if shift is not None:
                value = value + f.std * shift * rng.uniform(0.9, 1.3)
            out[f.key] = round(max(float(value), f.minimum), 3)
        return out

    def z_scores(self, values: dict[str, float]) -> dict[str, float]:
        return {f.key: (float(values[f.key]) - f.mean) / f.std for f in self.features}
