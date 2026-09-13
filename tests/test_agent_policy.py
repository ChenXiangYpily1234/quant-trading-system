from backend.app.agent_tools import invoke


def test_agent_has_no_production_or_holding_mutation_tools():
    for name in ("signal.set", "portfolio.upsert", "strategy.promote",
                 "approval.approve", "database.query", "shell.exec"):
        result = invoke(name, {})
        assert result.error.code == "tool_not_allowed"
