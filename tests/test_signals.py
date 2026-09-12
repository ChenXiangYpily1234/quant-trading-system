from backend.app.signals import compute_signal


def test_signal_is_deterministic():
    navs = [1 + i * 0.002 for i in range(30)]
    first = compute_signal(navs, [0.2, -0.1], "REAL")
    second = compute_signal(navs, [0.2, -0.1], "REAL")
    assert first == second
    assert first.status == "ok"
    assert 0 <= first.overall_score <= 100


def test_simulated_data_is_blocked():
    result = compute_signal([1.0] * 30, [], "SIMULATED")
    assert result.status == "blocked_simulated_data"
    assert result.overall_score is None
