"""Synthetic event generator for scenario packs; runs standalone or embedded in the model service."""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from typing import Iterator

import numpy as np

from .bus import make_bus
from .config import Settings
from .scenarios import Scenario, get_scenario

FIRST_ANOMALY_INDEX = 2  # inject an early anomaly so TTV measures the platform, not dice luck


def generate_events(scenario: Scenario, seed: int = 7, anomaly_rate: float = 0.1,
                    count: int | None = None) -> Iterator[dict]:
    """Deterministic event stream (given a seed); timestamps are stamped at emit time by the caller."""
    rng = np.random.default_rng(seed + 1)
    i = 0
    while count is None or i < count:
        entity = scenario.entities[int(rng.integers(len(scenario.entities)))]
        is_anomaly = i == FIRST_ANOMALY_INDEX or (i > FIRST_ANOMALY_INDEX and rng.random() < anomaly_rate)
        if is_anomaly:
            fault = scenario.faults[int(rng.integers(len(scenario.faults)))]
            features, kind = scenario.sample_fault(rng, fault.kind), fault.kind
        else:
            row = scenario.sample_normal(rng, 1)[0]
            features, kind = {k: round(float(v), 3) for k, v in zip(scenario.feature_keys, row)}, None
        yield {"id": f"{scenario.name}-{seed}-{i}", "scenario": scenario.name, "entity": entity,
               "features": features, "label": int(is_anomaly), "kind": kind}
        i += 1


async def run(bus, settings: Settings, count: int | None = None) -> int:
    scenario = get_scenario(settings.scenario)
    interval = 1.0 / settings.event_rate if settings.event_rate > 0 else 0.0
    sent = 0
    for event in generate_events(scenario, settings.seed, settings.anomaly_rate, count):
        event["ts"] = time.time()
        await bus.publish(settings.subject, event)
        sent += 1
        await asyncio.sleep(interval)
    return sent


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Publish synthetic scenario events to the bus")
    parser.add_argument("--count", type=int, default=None, help="stop after N events (default: run forever)")
    args = parser.parse_args()
    settings = Settings.from_env()
    bus = make_bus(settings.bus_url)
    await bus.connect()
    logging.getLogger("ttv.generator").info("publishing %s events to %s", settings.scenario, settings.subject)
    try:
        await run(bus, settings, args.count)
    finally:
        await bus.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
