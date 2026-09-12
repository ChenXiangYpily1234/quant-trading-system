import json
import logging
from typing import Any

logger = logging.getLogger("quantflow")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def event(name: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": name, **fields}, ensure_ascii=False, default=str))
