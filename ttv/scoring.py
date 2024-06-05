"""Anomaly scoring: an IsolationForest fitted on the scenario's synthetic baseline."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest

from .scenarios import Scenario

TRAIN_SIZE = 3000
TARGET_FPR = 0.01  # alert threshold = 99th percentile of baseline scores


class AnomalyScorer:
    def __init__(self, scenario: Scenario, seed: int = 7, target_fpr: float = TARGET_FPR):
        self.scenario = scenario
        rng = np.random.default_rng(seed)
        train = scenario.sample_normal(rng, TRAIN_SIZE)
        self.model = IsolationForest(n_estimators=100, random_state=seed, n_jobs=1).fit(train)
        baseline = self._raw(train)
        self.threshold = float(np.quantile(baseline, 1.0 - target_fpr))

    def _raw(self, matrix: np.ndarray) -> np.ndarray:
        return -self.model.score_samples(matrix)  # higher = more anomalous

    def score(self, values: dict[str, float]) -> tuple[float, bool]:
        row = np.array([[float(values[k]) for k in self.scenario.feature_keys]])
        score = float(self._raw(row)[0])
        return score, score > self.threshold
