"""End-to-end smoke checks, usable against a live cluster (HTTP) or an in-process app (TestClient)."""
from __future__ import annotations

import time
from typing import Callable

from .scenarios import get_scenario


class SmokeFailure(AssertionError):
    pass


def _wait(fn: Callable[[], object], timeout: float, what: str, interval: float = 1.0):
    deadline, last = time.time() + timeout, None
    while time.time() < deadline:
        try:
            result = fn()
            if result:
                return result
        except Exception as exc:  # connection refused while pods start, etc.
            last = exc
        time.sleep(interval)
    raise SmokeFailure(f"timed out after {timeout:.0f}s waiting for {what}" + (f" ({last})" if last else ""))


def run(model, dashboard, timeout: float = 120.0, log: Callable[[str], None] = print) -> list[str]:
    """`model` / `dashboard` expose .get/.post (httpx.Client or Starlette TestClient). Raises on failure."""
    passed: list[str] = []

    def ok(msg: str) -> None:
        passed.append(msg)
        log(f"  PASS  {msg}")

    _wait(lambda: model.get("/readyz").status_code == 200, timeout, "model service /readyz")
    ok("model service ready (event bus connected)")

    stats = _wait(lambda: (s := model.get("/stats").json())["processed"] >= 10 and s, timeout,
                  "events flowing through the bus")
    ok(f"events flowing end to end ({stats['processed']} scored)")

    stats = _wait(lambda: (s := model.get("/stats").json())["confusion"]["tp"] >= 1 and s, timeout,
                  "first true detection")
    if stats["first_insight_at"] is None:
        raise SmokeFailure("alerts recorded but no first-insight timestamp")
    ok("first insight produced"
       + (f" in {stats['time_to_first_insight_s']:.1f}s since start" if stats["time_to_first_insight_s"] is not None else ""))

    insights = model.get("/insights").json()
    if not insights or not all(i["summary"] and i["alert"] for i in insights):
        raise SmokeFailure("insights missing plain-English summaries")
    ok(f"insights carry summaries (source: {insights[0]['summary_source']})")

    state = model.get("/state").json()
    scenario = get_scenario(state["scenario"]["name"])
    extreme = {f.key: f.mean + 10 * f.std for f in scenario.features}
    normal = {f.key: f.mean for f in scenario.features}
    hit = model.post("/score", json={"entity": "smoke", "features": extreme}).json()
    if not (hit["alert"] and hit["summary"] and hit["severity"] == "critical"):
        raise SmokeFailure(f"extreme event not flagged critical: {hit}")
    miss = model.post("/score", json={"entity": "smoke", "features": normal}).json()
    if miss["alert"]:
        raise SmokeFailure(f"baseline event wrongly flagged: {miss}")
    if model.post("/score", json={"features": {"nope": 1}}).status_code != 422:
        raise SmokeFailure("malformed event not rejected with 422")
    ok("scoring API flags anomalies, passes baseline, rejects bad input")

    page = dashboard.get("/")
    if page.status_code != 200 or "TimeToValue" not in page.text:
        raise SmokeFailure("dashboard page not served")
    roi = _wait(lambda: (r := dashboard.get("/api/roi")).status_code == 200 and r.json(), timeout, "ROI endpoint")
    if roi["monthly"]["hours_saved"] <= 0:
        raise SmokeFailure(f"ROI shows no savings: {roi['monthly']}")
    ok(f"dashboard up; ROI estimate {roi['monthly']['hours_saved']} h/month saved")
    return passed
