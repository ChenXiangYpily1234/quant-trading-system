from typing import List, Literal
from pydantic import BaseModel, Field


class Explanation(BaseModel):
    headline: str = Field(max_length=80)
    summary: str = Field(max_length=400)
    key_points: List[str] = Field(default_factory=list, max_length=5)
    risk_note: str = Field(max_length=200)
    engine: Literal["llm", "deterministic_fallback"] = "deterministic_fallback"
