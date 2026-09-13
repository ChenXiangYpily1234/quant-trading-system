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
        CREATE TABLE IF NOT EXISTS experiments (
          experiment_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
          hypothesis TEXT NOT NULL, research_question TEXT NOT NULL,
          baseline TEXT NOT NULL, candidate TEXT NOT NULL,
          train_period TEXT NOT NULL, validation_period TEXT NOT NULL,
          test_period TEXT NOT NULL, benchmark TEXT NOT NULL,
          strategy_version TEXT, dataset_version TEXT, parameters TEXT NOT NULL,
          metrics TEXT NOT NULL, agent_thread_id TEXT,
          status TEXT NOT NULL CHECK(status IN ('draft','accepted','rejected','inconclusive')),
          conclusion TEXT NOT NULL, warnings TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS experiment_runs (
          run_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
          created_at TEXT NOT NULL, role TEXT NOT NULL, result TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS strategy_versions (
          version TEXT PRIMARY KEY, parent_version TEXT NOT NULL,
          change_description TEXT NOT NULL, experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
          created_by TEXT NOT NULL, created_at TEXT NOT NULL, metrics TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status = 'candidate')
        );
        CREATE TABLE IF NOT EXISTS dataset_versions (
          version TEXT PRIMARY KEY, created_at TEXT NOT NULL,
          source TEXT NOT NULL, manifest TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_runs (
          run_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL,
          skill TEXT, tools_called TEXT NOT NULL, tool_inputs TEXT NOT NULL,
          tool_outputs TEXT NOT NULL, approval_id TEXT, duration_ms INTEGER,
          final_result TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (
          approval_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
          action TEXT NOT NULL, risk_level TEXT NOT NULL,
          reason TEXT NOT NULL, diff TEXT NOT NULL, requested_by TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status = 'pending'),
          experiment_id TEXT REFERENCES experiments(experiment_id)
        );
        """)
