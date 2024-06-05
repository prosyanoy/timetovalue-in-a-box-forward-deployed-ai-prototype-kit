"""Registry of swappable scenario packs."""
from .base import Fault, Feature, RoiDefaults, Scenario
from .network_anomaly import NETWORK_ANOMALY
from .predictive_maintenance import PREDICTIVE_MAINTENANCE

SCENARIOS: dict[str, Scenario] = {s.name: s for s in (NETWORK_ANOMALY, PREDICTIVE_MAINTENANCE)}


def get_scenario(name: str) -> Scenario:
    try:
        return SCENARIOS[name]
    except KeyError:
        raise ValueError(f"unknown scenario {name!r}; choose one of: {', '.join(sorted(SCENARIOS))}") from None


__all__ = ["SCENARIOS", "Fault", "Feature", "RoiDefaults", "Scenario", "get_scenario"]
