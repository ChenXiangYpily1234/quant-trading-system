import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import config
from ..db.database import connect, initialize


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExperimentCreate(ResearchInput):
    hypothesis: str = Field(..., min_length=5, max_length=1000)
    research_question: str = Field(..., min_length=5, max_length=1000)
    baseline: str = Field(..., min_length=1, max_length=100)
    candidate: str = Field(..., min_length=1, max_length=100)
    train_period: str = Field(..., min_length=1, max_length=100)
    validation_period: str = Field(..., min_length=1, max_length=100)
    test_period: str = Field(..., min_length=1, max_length=100)
    benchmark: str = Field(..., min_length=1, max_length=100)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class CandidateCreate(ResearchInput):
    version: str = Field(..., pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,99}$")
    parent_version: str = Field(..., min_length=1, max_length=100)
    experiment_id: str
    change_description: str = Field(..., min_length=5, max_length=1000)
    created_by: str = Field(..., min_length=1, max_length=100)


class ApprovalCreate(ResearchInput):
    action: str = Field(..., pattern=r"^(signal_weights|risk_threshold|production_strategy|data_source|backtest_logic|transaction_cost|benchmark|quant_principle|database_schema|real_trade)$")
    risk_level: str = Field("high", pattern=r"^(medium|high)$")
    reason: str = Field(..., min_length=5, max_length=1000)
    diff: Dict[str, Any]
    requested_by: str = Field(..., min_length=1, max_length=100)
    experiment_id: Optional[str] = None


def create_experiment(req: ExperimentCreate) -> Dict[str, Any]:
    initialize()
    row = {"experiment_id": f"EXP-{uuid.uuid4().hex[:12]}", "created_at": _now(),
           **req.model_dump(), "strategy_version": None, "dataset_version": None,
           "metrics": {}, "agent_thread_id": None, "status": "draft",
           "conclusion": "", "warnings": []}
    with connect() as conn:
        conn.execute("""INSERT INTO experiments
          (experiment_id, created_at, hypothesis, research_question, baseline, candidate,
           train_period, validation_period, test_period, benchmark, strategy_version,
           dataset_version, parameters, metrics, agent_thread_id, status, conclusion, warnings)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (row["experiment_id"], row["created_at"], row["hypothesis"], row["research_question"],
           row["baseline"], row["candidate"], row["train_period"], row["validation_period"],
           row["test_period"], row["benchmark"], None, None,
           json.dumps(row["parameters"], ensure_ascii=False), "{}", None,
           "draft", "", "[]"))
    return row


def get_experiment(experiment_id: str) -> Optional[Dict[str, Any]]:
    initialize()
    with connect() as conn:
        raw = conn.execute("SELECT * FROM experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
    if raw is None:
        return None
    row = dict(raw)
    for key in ("parameters", "metrics", "warnings"):
        row[key] = json.loads(row[key])
    return row


def list_experiments(limit: int = 20) -> List[Dict[str, Any]]:
    initialize()
    with connect() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT experiment_id FROM experiments ORDER BY created_at DESC LIMIT ?", (limit,))]
    return [get_experiment(experiment_id) for experiment_id in ids]


def create_candidate(req: CandidateCreate) -> Dict[str, Any]:
    if req.version == config.SIGNAL_VERSION or req.version == req.parent_version:
        raise ValueError("候选版本不能覆盖现有或生产策略")
    if get_experiment(req.experiment_id) is None:
        raise ValueError("实验不存在")
    initialize()
    with connect() as conn:
        if req.parent_version != config.SIGNAL_VERSION and conn.execute(
                "SELECT 1 FROM strategy_versions WHERE version=?", (req.parent_version,)).fetchone() is None:
            raise ValueError("父版本不存在")
        row = {**req.model_dump(), "created_at": _now(), "metrics": {}, "status": "candidate"}
        conn.execute("""INSERT INTO strategy_versions
          (version, parent_version, change_description, experiment_id, created_by,
           created_at, metrics, status) VALUES (?,?,?,?,?,?,?,?)""",
          (req.version, req.parent_version, req.change_description, req.experiment_id,
           req.created_by, row["created_at"], "{}", "candidate"))
    return row


def request_approval(req: ApprovalCreate) -> Dict[str, Any]:
    if req.experiment_id and get_experiment(req.experiment_id) is None:
        raise ValueError("实验不存在")
    initialize()
    row = {"approval_id": f"APR-{uuid.uuid4().hex[:12]}", "created_at": _now(),
           **req.model_dump(), "status": "pending"}
    with connect() as conn:
        conn.execute("""INSERT INTO approvals
          (approval_id, created_at, action, risk_level, reason, diff,
           requested_by, status, experiment_id) VALUES (?,?,?,?,?,?,?,?,?)""",
          (row["approval_id"], row["created_at"], row["action"], row["risk_level"],
           row["reason"], json.dumps(row["diff"], ensure_ascii=False),
           row["requested_by"], "pending", row["experiment_id"]))
    return row
