"""Named, deterministic profiles; validated independently from any model."""

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType

from componentmatch_contracts.result import Metric

RULE_VERSION = "score-v0.2"
METRICS: tuple[Metric, ...] = ("price", "delivery", "quality", "on_time", "response")
_PERCENTAGES = {
    "balanced": (20, 25, 30, 20, 5),
    "cost": (45, 15, 20, 15, 5),
    "delivery": (20, 40, 20, 15, 5),
    "quality": (20, 15, 40, 20, 5),
}
PROFILES = MappingProxyType(
    {
        name: MappingProxyType(dict(zip(METRICS, (Decimal(n) / 100 for n in values), strict=True)))
        for name, values in _PERCENTAGES.items()
    }
)


def validate_weights(weights: Mapping[Metric, Decimal]) -> dict[Metric, Decimal]:
    if set(weights) != set(METRICS):
        raise ValueError("All five weight keys are required")
    if any(not isinstance(v, Decimal) or not v.is_finite() or v < 0 for v in weights.values()):
        raise ValueError("Weights must be finite nonnegative Decimals")
    if sum(weights.values()) != 1:
        raise ValueError("Weights must sum exactly to 1")
    return dict(weights)


def weights_for(profile: str) -> dict[Metric, Decimal]:
    return validate_weights(PROFILES[profile])
