import asyncio

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.agent.app_server import CodexAppServerRuntime
from backend.app.db import database


def test_agent_is_optional_and_token_gated(monkeypatch):
    monkeypatch.delenv("QUANTFLOW_AGENT_ENABLE", raising=False)
    monkeypatch.delenv("QUANTFLOW_AGENT_TOKEN", raising=False)
    client = TestClient(app)
    assert client.get("/api/agent/health").json()["status"] == "disabled"
    assert client.post("/api/agent/threads").status_code == 503
    monkeypatch.setenv("QUANTFLOW_AGENT_ENABLE", "true")
    monkeypatch.setenv("QUANTFLOW_AGENT_TOKEN", "test-token")
    assert client.post("/api/agent/threads", headers={"X-QuantFlow-Agent-Token": "wrong"}).status_code == 403


def test_runtime_events_exclude_reasoning(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "agent.db")
    runtime = CodexAppServerRuntime()
    runtime._threads.add("thread-1")
    runtime._record_notification({"method": "item/completed", "params": {
        "threadId": "thread-1", "turnId": "turn-1",
        "item": {"type": "reasoning", "content": ["private"]}}})
    runtime._record_notification({"method": "item/completed", "params": {
        "threadId": "thread-1", "turnId": "turn-1",
        "item": {"type": "agentMessage", "phase": "final_answer", "text": "evidence"}}})
    runtime._record_notification({"method": "turn/completed", "params": {
        "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed", "items": []}}})
    assert runtime.events("thread-1") == [{"cursor": 1, "type": "turn_completed",
                                            "turn_id": "turn-1", "status": "completed",
                                            "answer": "evidence"}]


def test_dynamic_tool_request_is_validated_and_audited(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "agent.db")
    runtime = CodexAppServerRuntime()
    runtime._threads.add("thread-1")
    sent = []

    async def capture(message):
        sent.append(message)

    runtime._write = capture
    asyncio.run(runtime._handle_server_request({"id": 7, "method": "item/tool/call",
        "params": {"threadId": "thread-1", "turnId": "turn-1", "namespace": "signal",
                   "tool": "set", "arguments": {"overall_score": 100}}}))
    assert sent[0]["result"]["success"] is False
    assert "tool_not_allowed" in sent[0]["result"]["contentItems"][0]["text"]
    with database.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
    assert count == 1


def test_research_runtime_rejects_developer_skill():
    runtime = CodexAppServerRuntime()
    runtime._threads.add("thread-1")
    try:
        asyncio.run(runtime.run_turn("thread-1", "修改评分", {"page": "research"}, "quant-developer"))
    except Exception as exc:
        assert "不属于只读研究" in str(exc)
    else:
        raise AssertionError("developer skill must not reach research runtime")
