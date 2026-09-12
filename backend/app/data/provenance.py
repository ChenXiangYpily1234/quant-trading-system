from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class DataSource(str, Enum):
    REAL = "REAL"
    STALE = "STALE"
    SIMULATED = "SIMULATED"


def provenance(source: str, provider: str, data_timestamp: Optional[str]) -> Dict[str, Any]:
    normalized = str(source).upper()
    if normalized not in {item.value for item in DataSource}:
        normalized = DataSource.STALE.value
    return {
        "data_source": normalized,
        "provider": provider,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data_timestamp": data_timestamp,
    }


def permits_research(source: str) -> bool:
    value = source.value if isinstance(source, DataSource) else str(source)
    return value.upper() == DataSource.REAL.value
