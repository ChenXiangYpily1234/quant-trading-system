import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quantflow.db"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize() -> None:
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS watchlist (
          code TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL DEFAULT '',
          note TEXT NOT NULL DEFAULT '', focus INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS portfolio (
          code TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', shares REAL NOT NULL,
          cost_nav REAL NOT NULL, CHECK(shares > 0), CHECK(cost_nav > 0)
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS alerts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, payload TEXT NOT NULL
        );
        """)
