import pytest

from ttv import roi
from ttv.cli import main
from ttv.scenarios import get_scenario

D = get_scenario("network-anomaly").roi


def inputs(**kw):
    base = dict(measured_detect_seconds=2.0, measured_recall=1.0, measured_fp_share=0.1)
    base.update(kw)
    return roi.RoiInputs.from_defaults(D, **base)


def test_known_numbers():
    r = roi.calculate(inputs(anomalies_per_month=10, baseline_detect_minutes=60, baseline_alerts_per_month=100,
                             baseline_fp_share=0.5, triage_minutes_per_alert=30, analyst_hourly_cost=100,
                             incident_cost_per_hour=1000, measured_detect_seconds=0, measured_fp_share=0.0))
    m = r["monthly"]
    assert m["exposure_hours_saved"] == 10.0 and m["exposure_cost_saved"] == 10_000
    assert m["false_alerts_baseline"] == 50 and m["false_alerts_with_kit"] == 0
    assert m["triage_hours_saved"] == 25.0 and m["triage_cost_saved"] == 2500
    assert m["hours_saved"] == 35.0 and r["annual"]["cost_saved"] == 150_000


def test_faster_detection_saves_more():
    slow = roi.calculate(inputs(measured_detect_seconds=3600))["monthly"]["hours_saved"]
    fast = roi.calculate(inputs(measured_detect_seconds=1))["monthly"]["hours_saved"]
    assert fast > slow


def test_lower_recall_and_more_false_positives_reduce_savings():
    good = roi.calculate(inputs())["monthly"]["cost_saved"]
    assert roi.calculate(inputs(measured_recall=0.5))["monthly"]["cost_saved"] < good
    assert roi.calculate(inputs(measured_fp_share=0.6))["monthly"]["cost_saved"] < good


def test_slower_than_baseline_never_negative_exposure():
    assert roi.calculate(inputs(measured_detect_seconds=10**6))["monthly"]["exposure_hours_saved"] == 0


@pytest.mark.parametrize("kw", [{"measured_fp_share": 1.0}, {"measured_recall": 1.5}, {"analyst_hourly_cost": -1}])
def test_validation(kw):
    with pytest.raises(ValueError):
        roi.calculate(inputs(**kw))


def test_from_stats_needs_measurements():
    empty = {"detection_latency_s": {"mean": None}, "recall": None, "false_positive_share": None}
    with pytest.raises(ValueError, match="not enough"):
        roi.from_stats(D, empty)
    full = {"detection_latency_s": {"mean": 0.1}, "recall": 0.9, "false_positive_share": 0.1}
    assert roi.from_stats(D, full, anomalies_per_month=5)["inputs"]["anomalies_per_month"] == 5


def test_cli_roi_manual(capsys):
    assert main(["roi", "--detect-seconds", "1.5", "--recall", "0.9", "--fp-share", "0.1", "--json"]) == 0
    assert '"hours_saved"' in capsys.readouterr().out
    assert main(["roi", "--detect-seconds", "1", "--fp-share", "1"]) == 2
