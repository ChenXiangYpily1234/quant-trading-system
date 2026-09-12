from typing import List, Optional
import numpy as np


def annualized(navs: List[float]) -> Optional[float]:
    if len(navs) < 3:
        return None
    rets = np.diff(np.asarray(navs, dtype=float)) / np.asarray(navs[:-1], dtype=float)
    return float(np.std(rets, ddof=1) * np.sqrt(252))


def risk_score(navs: List[float]) -> float:
    vol = annualized(navs)
    if vol is None:
        return 50.0
    return round(min(100.0, max(0.0, vol / 0.45 * 100)), 2)
