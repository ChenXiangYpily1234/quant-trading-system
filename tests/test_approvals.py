from backend.app.db import database
from backend.app.research.registry import ApprovalCreate, request_approval


def test_high_risk_change_only_creates_pending_request(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "research.db")
    row = request_approval(ApprovalCreate(action="signal_weights", risk_level="high",
                            reason="提议调整生产信号权重", diff={"old": 0.45, "new": 0.5},
                            requested_by="research-agent"))
    assert row["status"] == "pending"
    with database.connect() as conn:
        stored = conn.execute("SELECT status FROM approvals WHERE approval_id=?",
                              (row["approval_id"],)).fetchone()
    assert stored["status"] == "pending"
