"""极简内存缓存（带过期时间），用于净值/新闻的短时缓存，避免频繁抓取。"""
import time
from typing import Any, Optional, Dict


class TTLCache:
    def __init__(self, default_ttl: int = 60):
        self.default_ttl = default_ttl
        self._store: Dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None
        ts, value = item
        if time.time() - ts > self.default_ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        self._store[key] = (time.time(), value)

    def has(self, key: str) -> bool:
        return self.get(key) is not None


cache = TTLCache(default_ttl=60)
