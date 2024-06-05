"""`python -m ttv.cli`: up/down, demo, smoke, ROI calculator, scenario listing."""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace

import httpx

from . import roi
from .config import Settings
from .scenarios import SCENARIOS, get_scenario

ROI_FLAGS = ("anomalies_per_month", "baseline_detect_minutes", "baseline_alerts_per_month", "baseline_fp_share",
             "triage_minutes_per_alert", "analyst_hourly_cost", "incident_cost_per_hour")


def cmd_up(args) -> int:
    from . import kit

    kit.up(args.scenario)
    return 0


def cmd_down(_args) -> int:
    from . import kit

    kit.down()
    return 0


def cmd_scenarios(_args) -> int:
    for s in SCENARIOS.values():
        print(f"{s.name:24} {s.title}\n{'':24} {s.description}")
    return 0


def cmd_demo(args) -> int:
    """Run the whole pipeline in one process (in-memory bus) with the dashboard: no Docker needed."""
    import uvicorn

    from .service import create_app

    settings = replace(Settings.from_env(), scenario=args.scenario, bus_url="memory", embedded_generator=True,
                       start_epoch=time.time(), event_rate=args.rate)
    print(f"dashboard: http://localhost:{args.port}/   (Ctrl-C to stop)")
    uvicorn.run(create_app(settings, with_dashboard=True), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def cmd_smoke(args) -> int:
    from . import smoke

    if args.local:
        from fastapi.testclient import TestClient

        from .service import create_app

        settings = Settings(scenario=args.scenario, bus_url="memory", embedded_generator=True,
                            start_epoch=time.time(), event_rate=20.0)
        with TestClient(create_app(settings, with_dashboard=True)) as client:
            return _smoke(smoke, client, client, args.timeout)
    with httpx.Client(base_url=args.model_url, timeout=10) as model, \
            httpx.Client(base_url=args.dashboard_url, timeout=10) as dash:
        return _smoke(smoke, model, dash, args.timeout)


def _smoke(smoke, model, dash, timeout: float) -> int:
    print("smoke test:")
    try:
        passed = smoke.run(model, dash, timeout)
    except smoke.SmokeFailure as exc:
        print(f"  FAIL  {exc}")
        return 1
    print(f"smoke test passed ({len(passed)} checks)")
    return 0


def cmd_roi(args) -> int:
    from . import kit

    scenario = get_scenario(args.scenario)
    stats = None
    if args.url:
        stats = httpx.get(f"{args.url}/stats", timeout=5).json()
    elif kit.RUN_FILE.exists() and args.detect_seconds is None:
        record = json.loads(kit.RUN_FILE.read_text())
        stats = record["stats"]
        if record["scenario"] != args.scenario:
            print(f"note: last run used scenario {record['scenario']!r}; using its measurements with "
                  f"{args.scenario!r} assumptions", file=sys.stderr)
    overrides = {k: getattr(args, k) for k in ROI_FLAGS}
    try:
        if args.detect_seconds is not None:
            inp = roi.RoiInputs.from_defaults(scenario.roi, args.detect_seconds, args.recall, args.fp_share, **overrides)
            result = roi.calculate(inp)
            result["currency"] = scenario.roi.currency
        elif stats is not None:
            result = roi.from_stats(scenario.roi, stats, **overrides)
        else:
            print("no measurements: run `make up` first, pass --url, or give --detect-seconds", file=sys.stderr)
            return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    i, m, a, c = result["inputs"], result["monthly"], result["annual"], result["currency"]
    print(f"ROI estimate — {scenario.title}")
    print(f"  measured: detect in {i['measured_detect_seconds']:.2f}s (customer today: {i['baseline_detect_minutes']:.0f} min), "
          f"recall {i['measured_recall']:.0%}, false-positive share {i['measured_fp_share']:.0%} "
          f"(today {i['baseline_fp_share']:.0%})")
    print(f"  per month: {m['exposure_hours_saved']} h exposure avoided + {m['triage_hours_saved']} h triage "
          f"= {m['hours_saved']} h saved  ({c} {m['cost_saved']:,.0f})")
    print(f"  per year:  {a['hours_saved']:,.0f} h saved  ({c} {a['cost_saved']:,.0f})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ttv", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    names = sorted(SCENARIOS)

    s = sub.add_parser("up", help="deploy the stack to a local kind cluster and measure time-to-first-insight")
    s.add_argument("--scenario", choices=names, default="network-anomaly")
    s.set_defaults(fn=cmd_up)

    sub.add_parser("down", help="delete the kind cluster").set_defaults(fn=cmd_down)
    sub.add_parser("scenarios", help="list scenario packs").set_defaults(fn=cmd_scenarios)

    s = sub.add_parser("demo", help="run everything in one local process (no Docker/Kubernetes)")
    s.add_argument("--scenario", choices=names, default="network-anomaly")
    s.add_argument("--port", type=int, default=8090)
    s.add_argument("--rate", type=float, default=5.0)
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("smoke", help="end-to-end pipeline smoke test")
    s.add_argument("--local", action="store_true", help="in-process, no cluster needed")
    s.add_argument("--scenario", choices=names, default="network-anomaly", help="(--local only)")
    s.add_argument("--model-url", default="http://localhost:8081")
    s.add_argument("--dashboard-url", default="http://localhost:8080")
    s.add_argument("--timeout", type=float, default=120.0)
    s.set_defaults(fn=cmd_smoke)

    s = sub.add_parser("roi", help="convert measured detection speed / false positives into hours and cost saved")
    s.add_argument("--scenario", choices=names, default="network-anomaly")
    s.add_argument("--url", help="model service base URL to read live measurements from")
    s.add_argument("--detect-seconds", type=float, help="manual measurement instead of a live/last run")
    s.add_argument("--recall", type=float, default=0.9)
    s.add_argument("--fp-share", type=float, default=0.1)
    for flag in ROI_FLAGS:
        s.add_argument(f"--{flag.replace('_', '-')}", dest=flag, type=float, default=None)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_roi)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
