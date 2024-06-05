"""Plain-English insight summaries: optional local LLM, deterministic template fallback."""
from __future__ import annotations

import json
import logging
import urllib.request

from .scenarios import Scenario

log = logging.getLogger("ttv.summarizer")


def drivers(scenario: Scenario, values: dict[str, float], top: int = 3, min_z: float = 2.5) -> list[tuple[str, float]]:
    """Features that deviate most from baseline, largest first."""
    z = scenario.z_scores(values)
    ranked = sorted(z.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return [(k, v) for k, v in ranked[:top] if abs(v) >= min_z]


def diagnose(scenario: Scenario, values: dict[str, float]) -> str | None:
    """Pick the fault archetype whose signature best explains the deviations."""
    z = scenario.z_scores(values)
    best, best_score = None, 0.0
    for fault in scenario.faults:
        # cosine-like match: reward deviation in the signature's direction
        score = sum(min(z[k] * (1 if s > 0 else -1), 12.0) for k, s in fault.shifts.items() if k in z)
        score /= len(fault.shifts)
        if score > best_score:
            best, best_score = fault.kind, score
    return best if best_score >= 2.5 else None


def severity(scenario: Scenario, values: dict[str, float]) -> str:
    peak = max(abs(v) for v in scenario.z_scores(values).values())
    if peak >= 8:
        return "critical"
    if peak >= 5:
        return "high"
    return "medium"


def template_summary(scenario: Scenario, entity: str, values: dict[str, float], sev: str, kind: str | None) -> str:
    parts = []
    for key, z in drivers(scenario, values):
        f = scenario.feature(key)
        direction = "above" if z > 0 else "below"
        parts.append(f"{f.label} {values[key]:,.1f} {f.unit} ({abs(z):.1f}σ {direction} normal)")
    if kind:
        fault = scenario.fault(kind)
        head = f"{sev.upper()}: {scenario.entity_noun} {entity} shows {fault.title}."
        tail = f" Suggested action: {fault.action}."
    else:
        head = f"{sev.upper()}: {scenario.entity_noun} {entity} is behaving unusually."
        tail = " Suggested action: have an analyst review recent activity."
    body = " Drivers: " + "; ".join(parts) + "." if parts else " No single reading stands out; the combination is rare."
    return head + body + tail


class Summarizer:
    """Tries an OpenAI-compatible local LLM when configured; never fails the pipeline."""

    def __init__(self, scenario: Scenario, base_url: str = "", model: str = "", api_key: str = "", timeout: float = 4.0):
        self.scenario = scenario
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def summarize(self, entity: str, values: dict[str, float], sev: str, kind: str | None) -> tuple[str, str]:
        """Return (summary, source) where source is 'llm' or 'template'."""
        fallback = template_summary(self.scenario, entity, values, sev, kind)
        if not self.base_url:
            return fallback, "template"
        try:
            return self._llm(entity, values, sev, fallback), "llm"
        except Exception as exc:  # network, HTTP, JSON, timeout: all degrade gracefully
            log.warning("LLM unavailable (%s); using deterministic summary", exc)
            return fallback, "template"

    def _llm(self, entity: str, values: dict[str, float], sev: str, facts: str) -> str:
        prompt = (
            f"You are an operations analyst assistant for: {self.scenario.title}. "
            f"Rewrite these findings for {entity} as two plain-English sentences for a non-expert. "
            f"Keep every number. Severity: {sev}.\nFindings: {facts}\nReadings: {json.dumps(values)}"
        )
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 160,
        }).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (operator-configured URL)
            text = json.load(resp)["choices"][0]["message"]["content"].strip()
        if not text:
            raise ValueError("empty completion")
        return text
