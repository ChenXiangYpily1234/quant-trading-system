"""轻量 JSON 持久化：自选列表、持仓、提醒等用户数据落盘，重启不丢。"""
import json
import threading
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


def path_of(name: str) -> Path:
    return DATA_DIR / name


def load(name: str, default: Any) -> Any:
    p = path_of(name)
    if not p.exists():
        return default
    try:
        with _lock:
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(name: str, data: Any) -> None:
    p = path_of(name)
    try:
        with _lock:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
