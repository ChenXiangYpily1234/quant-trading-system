from typing import Literal, Optional
from pydantic import BaseModel


class SignalResult(BaseModel):
    trend_score: Optional[float] = None
    momentum_score: Optional[float] = None
    sentiment_score: Optional[float] = None
    risk_score: Optional[float] = None
    overall_score: Optional[float] = None
    confidence: float = 0.0
    state: Literal["positive", "neutral", "negative", "unavailable"]
    status: Literal["ok", "insufficient_data", "blocked_simulated_data"]
    signal_version: str
