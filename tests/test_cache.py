import time
from backend.app.cache import TTLCache


def test_per_key_ttl_is_honored():
    cache = TTLCache(default_ttl=10)
    cache.set("short", 1, ttl=0.01)
    cache.set("long", 2, ttl=1)
    time.sleep(0.02)
    assert cache.get("short") is None
    assert cache.get("long") == 2
