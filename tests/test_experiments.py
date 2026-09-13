from backend.app.agent_tools import invoke
from backend.app.db import database
from backend.app.research.registry import get_experiment


def test_experiment_starts_as_draft_without_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "research.db")
    result = invoke("experiment.create", {
        "hypothesis": "新闻情绪可改善样本外趋势信号",
        "research_question": "新闻情绪是否改善样本外表现？",
        "baseline": "signal-v1", "candidate": "signal-v1-news",
        "train_period": "2020-2022", "validation_period": "2023",
        "test_period": "2024", "benchmark": "buy_hold_nav"})
    assert result.success
    row = result.data["experiment"]
    assert row["status"] == "draft"
    assert row["metrics"] == {}
    assert get_experiment(row["experiment_id"]) == row
    assert invoke("experiment.get", {"experiment_id": row["experiment_id"]}).data["experiment"] == row
    assert invoke("experiment.list", {}).data["count"] == 1
