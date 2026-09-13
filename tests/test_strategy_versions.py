import pytest

from backend.app import config
from backend.app.db import database
from backend.app.research.registry import CandidateCreate, ExperimentCreate, create_candidate, create_experiment


def _experiment():
    return ExperimentCreate(hypothesis="候选策略是否改善样本外结果", research_question="样本外是否稳健？",
                            baseline=config.SIGNAL_VERSION, candidate="signal-v1-candidate",
                            train_period="2020", validation_period="2021", test_period="2022",
                            benchmark="buy_hold_nav")


def test_candidate_cannot_overwrite_production(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "research.db")
    experiment = create_experiment(_experiment())
    request = dict(version="signal-v1-candidate", parent_version=config.SIGNAL_VERSION,
                   experiment_id=experiment["experiment_id"], change_description="更改候选信号权重",
                   created_by="research-agent")
    candidate = create_candidate(CandidateCreate(**request))
    assert candidate["status"] == "candidate"
    with pytest.raises(ValueError, match="不能覆盖"):
        create_candidate(CandidateCreate(**{**request, "version": config.SIGNAL_VERSION}))
