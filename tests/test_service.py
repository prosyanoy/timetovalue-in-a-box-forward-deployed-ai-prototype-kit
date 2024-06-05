import time

import pytest
from fastapi.testclient import TestClient

from ttv import smoke
from ttv.bus import MemoryBus, make_bus
from ttv.config import Settings
from ttv.service import create_app


def settings(**kw):
    base = dict(bus_url="memory", embedded_generator=True, event_rate=50.0, start_epoch=time.time())
    base.update(kw)
    return Settings(**base)


@pytest.mark.parametrize("scenario", ["network-anomaly", "predictive-maintenance"])
def test_smoke_suite_passes_in_process(scenario):
    with TestClient(create_app(settings(scenario=scenario), with_dashboard=True)) as c:
        assert len(smoke.run(c, c, timeout=60, log=lambda _m: None)) == 6


def test_scenarios_are_swappable_via_settings():
    with TestClient(create_app(settings(scenario="predictive-maintenance", embedded_generator=False))) as c:
        assert c.get("/state").json()["scenario"]["name"] == "predictive-maintenance"
        bad = c.post("/score", json={"features": {"bytes_out_kb": 1}})
        assert bad.status_code == 422


def test_ready_only_after_bus_connect_and_no_generator_means_no_events():
    with TestClient(create_app(settings(embedded_generator=False))) as c:
        deadline = time.time() + 5
        while c.get("/readyz").status_code != 200 and time.time() < deadline:
            time.sleep(0.05)
        assert c.get("/readyz").json()["status"] == "ready"
        assert c.get("/stats").json()["processed"] == 0
        assert c.get("/api/roi").status_code == 404  # dashboard not mounted


def test_dashboard_roi_conflict_before_measurements():
    with TestClient(create_app(settings(embedded_generator=False), with_dashboard=True)) as c:
        assert c.get("/api/roi").status_code == 409
        assert "TimeToValue" in c.get("/").text


def test_make_bus_selects_backend():
    assert isinstance(make_bus("memory"), MemoryBus)
    assert make_bus("nats://x:4222").__class__.__name__ == "NatsBus"


def test_memory_bus_roundtrip():
    import asyncio

    got = []

    async def go():
        bus = MemoryBus()
        async def h(e): got.append(e)
        await bus.subscribe("s", h)
        await bus.publish("s", {"a": 1})
        await bus.publish("other", {"a": 2})

    asyncio.run(go())
    assert got == [{"a": 1}]


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SCENARIO", "predictive-maintenance")
    monkeypatch.setenv("TTV_START_EPOCH", "123.5")
    monkeypatch.setenv("EVENT_RATE", "")
    s = Settings.from_env()
    assert (s.scenario, s.start_epoch, s.event_rate) == ("predictive-maintenance", 123.5, 5.0)
