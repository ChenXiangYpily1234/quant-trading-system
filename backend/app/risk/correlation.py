from typing import Dict, List, Any
import numpy as np


def correlation_matrix(series: Dict[str, List[float]]) -> Dict[str, Any]:
    codes = list(series)
    if not codes or min((len(series[c]) for c in codes), default=0) < 3:
        return {"status": "insufficient_data", "codes": codes, "matrix": []}
    size = min(len(series[c]) for c in codes)
    returns = [np.diff(np.asarray(series[c][-size:], dtype=float)) / np.asarray(series[c][-size:-1], dtype=float) for c in codes]
    return {"status": "ok", "codes": codes, "matrix": np.corrcoef(returns).round(4).tolist()}
