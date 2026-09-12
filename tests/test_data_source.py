from backend.app.data.provenance import DataSource, permits_research, provenance
from backend.app import fund_data


def test_only_real_data_permits_research():
    assert permits_research(DataSource.REAL)
    assert not permits_research(DataSource.STALE)
    assert not permits_research(DataSource.SIMULATED)


def test_provenance_has_required_fields():
    result = provenance("REAL", "provider", "2026-01-01")
    assert set(result) == {"data_source", "provider", "fetched_at", "data_timestamp"}


def test_disabling_simulation_still_attempts_real_provider(monkeypatch):
    called = []
    monkeypatch.setattr(fund_data.config, "ALLOW_SIMULATED_DATA", False)
    monkeypatch.setattr(fund_data, "fetch_nav_real", lambda code, days: called.append(code) or None)
    points, source = fund_data.get_nav("000001", 20)
    assert called == ["000001"]
    assert points == []
    assert source == "STALE"
