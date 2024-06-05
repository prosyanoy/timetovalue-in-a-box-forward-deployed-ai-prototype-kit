"""ROI model: turn measured detection speed and false-positive behaviour into hours and money saved."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .scenarios import RoiDefaults

MONTHS_PER_YEAR = 12


@dataclass(frozen=True)
class RoiInputs:
    anomalies_per_month: float
    baseline_detect_minutes: float
    baseline_alerts_per_month: float
    baseline_fp_share: float
    triage_minutes_per_alert: float
    analyst_hourly_cost: float
    incident_cost_per_hour: float
    # measured by the kit
    measured_detect_seconds: float
    measured_recall: float
    measured_fp_share: float

    @classmethod
    def from_defaults(cls, d: RoiDefaults, measured_detect_seconds: float, measured_recall: float,
                      measured_fp_share: float, **overrides: float) -> "RoiInputs":
        base = {k: v for k, v in asdict(d).items() if k != "currency"}
        base.update({k: v for k, v in overrides.items() if v is not None})
        return cls(measured_detect_seconds=measured_detect_seconds, measured_recall=measured_recall,
                   measured_fp_share=measured_fp_share, **base)

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if value < 0:
                raise ValueError(f"{name} must be >= 0")
        for name in ("baseline_fp_share", "measured_recall", "measured_fp_share"):
            if getattr(self, name) > 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.measured_fp_share >= 1:
            raise ValueError("measured_fp_share must be < 1")


def calculate(inp: RoiInputs) -> dict:
    """Monthly and annual savings.

    * Detection: each anomaly the kit catches is noticed after ``measured_detect_seconds``
      instead of ``baseline_detect_minutes``; the avoided exposure is priced at ``incident_cost_per_hour``.
      Missed anomalies (1 - recall) keep today's detection time, so they earn nothing.
    * Triage: false alerts are derived from the measured false-positive share of alerts, relative to
      today's volume of false alerts, and priced at analyst time.
    """
    inp.validate()
    caught = inp.anomalies_per_month * inp.measured_recall
    saved_per_anomaly_h = max(inp.baseline_detect_minutes / 60 - inp.measured_detect_seconds / 3600, 0.0)
    exposure_hours_saved = caught * saved_per_anomaly_h
    exposure_cost_saved = exposure_hours_saved * inp.incident_cost_per_hour

    baseline_false = inp.baseline_alerts_per_month * inp.baseline_fp_share
    kit_false = caught * inp.measured_fp_share / (1 - inp.measured_fp_share)
    false_alerts_avoided = baseline_false - kit_false
    triage_hours_saved = false_alerts_avoided * inp.triage_minutes_per_alert / 60
    triage_cost_saved = triage_hours_saved * inp.analyst_hourly_cost

    monthly_hours = exposure_hours_saved + triage_hours_saved
    monthly_cost = exposure_cost_saved + triage_cost_saved
    return {
        "inputs": asdict(inp),
        "monthly": {
            "anomalies_caught": round(caught, 2),
            "exposure_hours_saved": round(exposure_hours_saved, 1),
            "exposure_cost_saved": round(exposure_cost_saved, 2),
            "false_alerts_baseline": round(baseline_false, 1),
            "false_alerts_with_kit": round(kit_false, 1),
            "triage_hours_saved": round(triage_hours_saved, 1),
            "triage_cost_saved": round(triage_cost_saved, 2),
            "hours_saved": round(monthly_hours, 1),
            "cost_saved": round(monthly_cost, 2),
        },
        "annual": {
            "hours_saved": round(monthly_hours * MONTHS_PER_YEAR, 1),
            "cost_saved": round(monthly_cost * MONTHS_PER_YEAR, 2),
        },
    }


def from_stats(scenario_roi: RoiDefaults, stats: dict, **overrides: float) -> dict:
    """Build the ROI result from a /stats snapshot; needs at least one detection and one alert."""
    lat = stats["detection_latency_s"]["mean"]
    recall, fp_share = stats["recall"], stats["false_positive_share"]
    if lat is None or recall is None or fp_share is None:
        raise ValueError("not enough measurements yet (need at least one detection)")
    inp = RoiInputs.from_defaults(scenario_roi, lat, recall, fp_share, **overrides)
    result = calculate(inp)
    result["currency"] = scenario_roi.currency
    return result
