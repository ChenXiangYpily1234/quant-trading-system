import os
import shutil
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .app_server import AgentUnavailable, CodexAppServerRuntime

router = APIRouter(prefix="/api/agent", tags=["agent"])
_runtime: Optional[CodexAppServerRuntime] = None


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(..., min_length=1, max_length=2000)
    page: str = Field("research", pattern=r"^(research|fund_detail|backtest|portfolio)$")
    fund_code: Optional[str] = Field(None, pattern=r"^\d{6}$")
    skill: Literal["market-researcher", "signal-auditor", "backtest-auditor",
                   "strategy-researcher", "portfolio-analyst", "backtest-red-team"] = "market-researcher"


def _authorized(token: Optional[str]) -> None:
    expected = os.getenv("QUANTFLOW_AGENT_TOKEN")
    if os.getenv("QUANTFLOW_AGENT_ENABLE", "false").lower() != "true" or not expected:
        raise HTTPException(status_code=503, detail="Agent 未启用或未配置访问令牌")
    if token != expected:
        raise HTTPException(status_code=403, detail="Agent 访问令牌无效")


def _get_runtime() -> CodexAppServerRuntime:
    global _runtime
    if _runtime is None:
        _runtime = CodexAppServerRuntime(_executable())
    return _runtime


def _executable() -> str:
    configured = os.getenv("QUANTFLOW_CODEX_BIN")
    if configured:
        return configured
    bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    return str(bundled) if bundled.is_file() else "codex"


@router.get("/health")
def agent_health() -> Dict[str, Any]:
    enabled = os.getenv("QUANTFLOW_AGENT_ENABLE", "false").lower() == "true"
    configured = bool(os.getenv("QUANTFLOW_AGENT_TOKEN")) and bool(shutil.which(_executable()))
    active = bool(_runtime and _runtime.process and _runtime.process.returncode is None)
    verified = bool(active and _runtime.integration_verified)
    return {"status": ("connected_verified" if verified else "connected_unverified") if active
            else ("configured_unverified" if enabled and configured else "disabled"),
            "enabled": enabled, "integration_verified": verified}


@router.post("/threads")
async def create_thread(x_quantflow_agent_token: Optional[str] = Header(None)):
    _authorized(x_quantflow_agent_token)
    try:
        return {"thread_id": await _get_runtime().create_thread()}
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/threads/{thread_id}/turns")
async def run_turn(thread_id: str, req: TurnRequest,
                   x_quantflow_agent_token: Optional[str] = Header(None)):
    _authorized(x_quantflow_agent_token)
    try:
        turn_id = await _get_runtime().run_turn(thread_id, req.prompt,
                                                {"page": req.page, "fund_code": req.fund_code}, req.skill)
        return {"thread_id": thread_id, "turn_id": turn_id, "status": "in_progress"}
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/threads/{thread_id}/events")
def events(thread_id: str, after: int = 0, x_quantflow_agent_token: Optional[str] = Header(None)):
    _authorized(x_quantflow_agent_token)
    try:
        return {"events": _get_runtime().events(thread_id, after)}
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/threads/{thread_id}/turns/{turn_id}/cancel")
async def cancel(thread_id: str, turn_id: str, x_quantflow_agent_token: Optional[str] = Header(None)):
    _authorized(x_quantflow_agent_token)
    try:
        await _get_runtime().cancel(thread_id, turn_id)
        return {"status": "cancelling"}
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def shutdown_runtime() -> None:
    global _runtime
    if _runtime is not None:
        await _runtime.close()
        _runtime = None
