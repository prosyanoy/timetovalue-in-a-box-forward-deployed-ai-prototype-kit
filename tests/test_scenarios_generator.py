import numpy as np
import pytest

from ttv.generator import FIRST_ANOMALY_INDEX, generate_events
from ttv.scenarios import SCENARIOS, get_scenario


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_events_are_deterministic_and_complete(name):
    sc = get_scenario(name)
    a = list(generate_events(sc, seed=3, count=50))
    b = list(generate_events(sc, seed=3, count=50))
    assert a == b
    assert all(set(e["features"]) == set(sc.feature_keys) for e in a)
    assert a[FIRST_ANOMALY_INDEX]["label"] == 1
    assert all(e["entity"] in sc.entities for e in a)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_fault_samples_deviate_in_signature_direction(name):
    sc = get_scenario(name)
    rng = np.random.default_rng(0)
    for fault in sc.faults:
        z = sc.z_scores(sc.sample_fault(rng, fault.kind))
        for key, shift in fault.shifts.items():
            assert z[key] * shift > 0 and abs(z[key]) > 1.5


def test_anomaly_rate_roughly_respected():
    sc = get_scenario("network-anomaly")
    events = list(generate_events(sc, seed=1, anomaly_rate=0.2, count=2000))
    assert 0.15 < sum(e["label"] for e in events) / len(events) < 0.25


def test_unknown_scenario_message():
    with pytest.raises(ValueError, match="network-anomaly"):
        get_scenario("nope")
