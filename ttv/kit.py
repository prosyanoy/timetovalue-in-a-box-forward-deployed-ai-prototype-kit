"""Cluster orchestration for `make up`: kind + docker + helm, with the time-to-first-insight stopwatch."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RUN_FILE = ROOT / ".ttv" / "last_run.json"
CLUSTER = "ttv"
IMAGE = "ttv:local"
MODEL_URL = "http://localhost:8081"
DASHBOARD_URL = "http://localhost:8080"


def _run(*cmd: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check, cwd=ROOT, text=True, capture_output=capture)


def require_tools() -> None:
    missing = [t for t in ("docker", "kind", "helm", "kubectl") if shutil.which(t) is None]
    if missing:
        raise SystemExit(f"missing required tools: {', '.join(missing)} (see README 'Prerequisites')")


def up(scenario: str, timeout: float = 600.0) -> dict:
    require_tools()
    start = time.time()  # the stopwatch starts here, before any cluster work
    existing = _run("kind", "get", "clusters", capture=True).stdout.split()
    created = CLUSTER not in existing
    if created:
        _run("kind", "create", "cluster", "--name", CLUSTER, "--config", "deploy/kind/kind-config.yaml", "--wait", "120s")
    _run("docker", "build", "-t", IMAGE, ".")
    _run("kind", "load", "docker-image", IMAGE, "--name", CLUSTER)
    llm = os.environ.get("LLM_BASE_URL", "")  # optional; must be reachable from inside the cluster
    _run("helm", "upgrade", "--install", "ttv", "deploy/helm/ttv", "--namespace", "ttv", "--create-namespace",
         "--set", f"scenario={scenario}", "--set-string", f"startEpoch={start:.3f}",
         "--set-string", f"llm.baseUrl={llm}", "--set-string", f"llm.model={os.environ.get('LLM_MODEL', 'llama3.2')}",
         "--wait", "--timeout", "5m")
    print("stack deployed; waiting for the first insight…", flush=True)
    stats = wait_for_first_insight(MODEL_URL, timeout)
    record = {
        "scenario": scenario,
        "cluster_created": created,
        "time_to_first_insight_s": stats["time_to_first_insight_s"],
        "finished_at": time.time(),
        "stats": stats,
    }
    RUN_FILE.parent.mkdir(exist_ok=True)
    RUN_FILE.write_text(json.dumps(record, indent=2))
    print(f"\n⏱  time to first insight: {record['time_to_first_insight_s']:.1f}s "
          f"({'cold start incl. cluster creation' if created else 'warm: cluster already existed'})")
    print(f"   dashboard: {DASHBOARD_URL}    model API: {MODEL_URL}/docs    ROI: make roi")
    return record


def wait_for_first_insight(model_url: str, timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            stats = httpx.get(f"{model_url}/stats", timeout=3).json()
            if stats.get("time_to_first_insight_s") is not None:
                return stats
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit(f"no insight within {timeout:.0f}s; check `kubectl -n ttv get pods`")


def down() -> None:
    require_tools()
    _run("kind", "delete", "cluster", "--name", CLUSTER)
