import json
import time

import pytest

from ttv.generator import generate_events
from ttv.metrics import Metrics
from ttv.pipeline import Pipeline
from ttv.scenarios import SCENARIOS, get_scenario
from ttv.scoring import AnomalyScorer
from ttv.summarizer import Summarizer, diagnose, severity, template_summary


@pytest.fixture(scope="module", params=sorted(SCENARIOS))
def scenario(request):
    return get_scenario(request.param)


@pytest.fixture(scope="module")
def scorer(scenario):
    return AnomalyScorer(scenario)


def test_scorer_separates_baseline_from_extremes(scenario, scorer):
    normal = {f.key: f.mean for f in scenario.features}
    extreme = {f.key: f.mean + 10 * f.std for f in scenario.features}
    assert scorer.score(normal)[1] is False
    assert scorer.score(extreme)[1] is True
    assert scorer.score(extreme)[0] > scorer.score(normal)[0]


def test_diagnosis_matches_injected_fault(scenario):
    import numpy as np

    rng = np.random.default_rng(5)
    for fault in scenario.faults:
        hits = sum(diagnose(scenario, scenario.sample_fault(rng, fault.kind)) == fault.kind for _ in range(30))
        assert hits >= 27


def test_template_summary_is_deterministic_and_informative(scenario):
    import numpy as np

    fault = scenario.faults[0]
    values = scenario.sample_fault(np.random.default_rng(1), fault.kind)
    sev = severity(scenario, values)
    s1 = template_summary(scenario, "x1", values, sev, fault.kind)
    assert s1 == template_summary(scenario, "x1", values, sev, fault.kind)
    assert "x1" in s1 and fault.title in s1 and fault.action in s1 and "σ" in s1


def test_llm_failure_falls_back_to_template(scenario):
    values = {f.key: f.mean + 8 * f.std for f in scenario.features}
    # port 9 (discard) on localhost: connection refused -> must degrade, not raise
    summ = Summarizer(scenario, base_url="http://127.0.0.1:9/v1", model="m", timeout=0.5)
    text, source = summ.summarize("e1", values, "critical", None)
    assert source == "template" and "e1" in text


def test_llm_success_path(scenario, monkeypatch):
    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"choices": [{"message": {"content": " Plain words. "}}]}).encode()

    seen = {}

    def fake_open(req, timeout):
        seen["url"] = req.full_url
        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    values = {f.key: f.mean for f in scenario.features}
    text, source = Summarizer(scenario, "http://llm/v1/", "m").summarize("e1", values, "medium", None)
    assert (text, source) == ("Plain words.", "llm")
    assert seen["url"] == "http://llm/v1/chat/completions"


def test_pipeline_end_to_end_metrics(scenario, scorer):
    metrics = Metrics(start_epoch=time.time() - 1)
    pipe = Pipeline(scenario, scorer, Summarizer(scenario), metrics)
    for event in generate_events(scenario, count=600):
        event["ts"] = time.time()
        pipe.process(event)
    s = metrics.snapshot()
    assert s["processed"] == 600
    assert s["recall"] > 0.85
    assert s["false_positive_rate"] < 0.05
    assert 0 < s["time_to_first_insight_s"] < 30
    assert s["detection_latency_s"]["mean"] < 1
    assert all(i["summary"] for i in metrics.recent_insights())


def test_pipeline_rejects_bad_events(scenario, scorer):
    pipe = Pipeline(scenario, scorer, Summarizer(scenario), Metrics())
    with pytest.raises(ValueError, match="features"):
        pipe.process({"entity": "x"})
    with pytest.raises(ValueError, match="missing"):
        pipe.process({"features": {"nope": 1}})


def test_metrics_confusion_matrix():
    m = Metrics(start_epoch=100.0)
    mk = lambda alert: {"alert": alert, "latency_s": 0.5}
    m.record(mk(True), 1, now=103.0)
    m.record(mk(True), 0, now=104.0)
    m.record(mk(False), 1)
    m.record(mk(False), 0)
    s = m.snapshot()
    assert s["confusion"] == {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
    assert s["time_to_first_insight_s"] == 3.0
    assert s["precision"] == s["recall"] == s["false_positive_share"] == 0.5
