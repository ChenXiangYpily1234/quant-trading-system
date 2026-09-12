from typing import List
import numpy as np


def score(navs: List[float]) -> float:
    if len(navs) < 20:
        return 50.0
    latest = navs[-1]
    ma5, ma20 = float(np.mean(navs[-5:])), float(np.mean(navs[-20:]))
    raw = 50 + 600 * (latest / ma20 - 1) + 300 * (ma5 / ma20 - 1)
    return round(min(100.0, max(0.0, raw)), 2)
