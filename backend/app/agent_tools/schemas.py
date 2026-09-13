from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FundCode(StrictInput):
    code: str = Field(..., pattern=r"^\d{6}$")


class FundSearch(StrictInput):
    q: str = Field(..., min_length=1, max_length=60)
    limit: int = Field(10, ge=1, le=20)


class FundWindow(FundCode):
    days: int = Field(60, ge=20, le=400)


class HistoryWindow(FundCode):
    days: int = Field(60, ge=20, le=120)


class BacktestRequest(FundCode):
    strategy: str = Field("ma_cross", pattern=r"^(ma_cross|momentum|buy_hold)$")
    short: int = Field(5, ge=2, le=120)
    long: int = Field(20, ge=3, le=250)
    days: int = Field(250, ge=40, le=400)
    fee_bps: float = Field(15.0, ge=0, le=200)


class NewsSearch(StrictInput):
    q: str = Field(..., min_length=1, max_length=80)
    limit: int = Field(10, ge=1, le=10)


class ExperimentId(StrictInput):
    experiment_id: str = Field(..., pattern=r"^EXP-[0-9a-f]{12}$")


class ExperimentList(StrictInput):
    limit: int = Field(20, ge=1, le=100)


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ToolResult(BaseModel):
    success: bool
    tool: str
    data: Optional[Dict[str, Any]] = None
    provenance: Optional[Dict[str, Any]] = None
    warnings: List[str] = Field(default_factory=list)
    error: Optional[ToolError] = None


def success(tool: str, data: Dict[str, Any], provenance: Dict[str, Any],
            warnings: Optional[List[str]] = None) -> ToolResult:
    return ToolResult(success=True, tool=tool, data=data, provenance=provenance,
                      warnings=warnings or [])


def failure(tool: str, code: str, message: str, retryable: bool = False) -> ToolResult:
    return ToolResult(success=False, tool=tool,
                      error=ToolError(code=code, message=message, retryable=retryable))
