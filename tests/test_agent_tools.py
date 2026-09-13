from backend.app.agent_tools import invoke
from backend.app import fund_data
from backend.app.schemas import NavPoint


def _real_points():
    return [NavPoint(date=f"2026-01-{i + 1:02d}", nav=1 + i * 0.002) for i in range(30)]


def test_signal_is_core_result_and_deterministic(monkeypatch):
    monkeypatch.setattr(fund_data, "get_nav", lambda code, days: (_real_points(), "REAL"))
    from backend.app import main
    main._fund_cache.clear()
    a = invoke("signal.get", {"code": "005844", "days": 30})
    b = invoke("signal.get", {"code": "005844", "days": 30})
    assert a.success and b.success
    assert a.data == b.data
    assert a.data["signal"]["signal_version"] == main.config.SIGNAL_VERSION
    main._fund_cache.clear()


def test_simulated_data_cannot_produce_research_result(monkeypatch):
    monkeypatch.setattr(fund_data, "get_nav", lambda code, days: (_real_points(), "SIMULATED"))
    from backend.app import main
    main._fund_cache.clear()
    for tool in ("signal.get", "risk.fund", "backtest.run", "fund.snapshot"):
        result = invoke(tool, {"code": "005844"})
        assert not result.success
        assert result.error.code == "insufficient_evidence"
    main._fund_cache.clear()


def test_sample_news_is_not_evidence(monkeypatch):
    from backend.app import main
    from backend.app.schemas import NewsList
    monkeypatch.setattr(main, "_fetch_news_cached", lambda: NewsList(items=[], total=0,
                         source_note="内置示例资讯（降级）"))
    result = invoke("news.search", {"q": "基金"})
    assert not result.success
    assert result.error.code == "insufficient_evidence"


def test_page_and_tool_use_same_news_neutral_signal(monkeypatch):
    from backend.app import main
    from backend.app.schemas import NewsItem, NewsList
    monkeypatch.setattr(fund_data, "get_nav", lambda code, days: (_real_points(), "REAL"))
    main._fund_cache.clear()
    main._state_cache.clear()
    news = NewsList(items=[NewsItem(title="利好", link="https://example.test", source="example",
                                    sentiment=1.0, relevance=5)], total=1, source_note="实时抓取")
    page = main.build_state("005844", {"name": "基金"}, news, days=30)
    tool = invoke("signal.get", {"code": "005844", "days": 30})
    assert page["signal"] == tool.data["signal"]
    main._fund_cache.clear()
    main._state_cache.clear()
