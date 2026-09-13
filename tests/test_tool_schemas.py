from backend.app.agent_tools import invoke, tool_specs


def test_invalid_and_unknown_calls_fail_closed():
    invalid = invoke("signal.get", {"code": "005844", "overall_score": 100})
    unknown = invoke("signal.set", {"code": "005844", "overall_score": 100})
    assert invalid.error.code == "invalid_input"
    assert unknown.error.code == "tool_not_allowed"
    assert invalid.data is None and unknown.data is None


def test_specs_are_namespaced_pydantic_schemas():
    specs = tool_specs()
    assert {spec["name"] for spec in specs} >= {"fund", "signal", "risk"}
    signal = next(spec for spec in specs if spec["name"] == "signal")
    assert signal["tools"][0]["inputSchema"]["additionalProperties"] is False
