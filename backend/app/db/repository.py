import json
import shutil
from pathlib import Path
from typing import Any, Dict, List
from .database import connect, initialize


class Repository:
    def __init__(self) -> None:
        initialize()

    def migrate_json_once(self, data_dir: Path) -> None:
        mappings = {"watchlist.json": "watchlist", "holdings.json": "portfolio"}
        for filename, table in mappings.items():
            path = data_dir / filename
            with connect() as conn:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count or not path.exists():
                continue
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
                if table == "watchlist":
                    self.replace_watchlist(rows)
                else:
                    for row in rows:
                        self.upsert_holding(row)
                backup = path.with_suffix(path.suffix + ".bak")
                if not backup.exists():
                    shutil.copy2(path, backup)
            except (OSError, ValueError, TypeError):
                continue

    def list_watchlist(self) -> List[Dict[str, Any]]:
        with connect() as conn:
            return [dict(r) | {"focus": bool(r["focus"])} for r in conn.execute("SELECT * FROM watchlist ORDER BY rowid")]

    def replace_watchlist(self, rows: List[Dict[str, Any]]) -> None:
        with connect() as conn:
            conn.execute("DELETE FROM watchlist")
            conn.executemany("INSERT INTO watchlist(code,name,category,note,focus) VALUES(?,?,?,?,?)",
                             [(r["code"], r.get("name", r["code"]), r.get("category", "其他"),
                               r.get("note", ""), int(bool(r.get("focus")))) for r in rows])

    def upsert_watch(self, row: Dict[str, Any]) -> Dict[str, Any]:
        with connect() as conn:
            conn.execute("INSERT INTO watchlist(code,name,category,note,focus) VALUES(?,?,?,?,?) "
                         "ON CONFLICT(code) DO UPDATE SET name=excluded.name,category=excluded.category,note=excluded.note,focus=excluded.focus",
                         (row["code"], row["name"], row.get("category", "其他"), row.get("note", ""), int(bool(row.get("focus")))))
        return row

    def delete_watch(self, code: str) -> bool:
        with connect() as conn:
            return conn.execute("DELETE FROM watchlist WHERE code=?", (code,)).rowcount > 0

    def list_holdings(self) -> List[Dict[str, Any]]:
        with connect() as conn:
            return [dict(r) for r in conn.execute("SELECT code,name,shares,cost_nav FROM portfolio ORDER BY rowid")]

    def upsert_holding(self, row: Dict[str, Any]) -> Dict[str, Any]:
        with connect() as conn:
            conn.execute("INSERT INTO portfolio(code,name,shares,cost_nav) VALUES(?,?,?,?) "
                         "ON CONFLICT(code) DO UPDATE SET name=excluded.name,shares=excluded.shares,cost_nav=excluded.cost_nav",
                         (row["code"], row.get("name", ""), row["shares"], row["cost_nav"]))
        return row

    def delete_holding(self, code: str) -> bool:
        with connect() as conn:
            return conn.execute("DELETE FROM portfolio WHERE code=?", (code,)).rowcount > 0


repository = Repository()
