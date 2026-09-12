from typing import Iterable


def score(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        return 50.0
    return round(min(100.0, max(0.0, 50 + 50 * sum(vals) / len(vals))), 2)
