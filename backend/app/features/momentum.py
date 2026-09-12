from typing import List


def score(navs: List[float]) -> float:
    if len(navs) < 6 or navs[-6] == 0:
        return 50.0
    ret5 = navs[-1] / navs[-6] - 1
    ret20 = navs[-1] / navs[-21] - 1 if len(navs) >= 21 and navs[-21] else ret5
    raw = 50 + 350 * ret5 + 180 * ret20
    return round(min(100.0, max(0.0, raw)), 2)
