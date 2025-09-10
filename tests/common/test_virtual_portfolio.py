import pytest

from backend.common import virtual_portfolio


def test_virtual_portfolio_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(virtual_portfolio, "VIRTUAL_PORTFOLIO_DIR", tmp_path)

    vp = virtual_portfolio.VirtualPortfolio(
        id="demo",
        name="Demo",
        holdings=[
            virtual_portfolio.VirtualHolding(ticker="AAA", units=1.23),
            virtual_portfolio.VirtualHolding(ticker="BBB", units=4.56),
        ],
    )

    virtual_portfolio.save_virtual_portfolio(vp)
    loaded = virtual_portfolio.load_virtual_portfolio("demo")

    assert loaded is not None
    assert loaded.model_dump() == vp.model_dump()


def test_list_and_delete_virtual_portfolios(tmp_path, monkeypatch):
    monkeypatch.setattr(virtual_portfolio, "VIRTUAL_PORTFOLIO_DIR", tmp_path)

    vp1 = virtual_portfolio.VirtualPortfolio(id="vp1", name="One")
    vp2 = virtual_portfolio.VirtualPortfolio(id="vp2", name="Two")

    virtual_portfolio.save_virtual_portfolio(vp1)
    virtual_portfolio.save_virtual_portfolio(vp2)

    metas = virtual_portfolio.list_virtual_portfolio_metadata()
    assert [(m.id, m.name) for m in metas] == [("vp1", "One"), ("vp2", "Two")]

    portfolios = virtual_portfolio.list_virtual_portfolios()
    assert [p.id for p in portfolios] == ["vp1", "vp2"]

    virtual_portfolio.delete_virtual_portfolio("vp1")
    assert virtual_portfolio.load_virtual_portfolio("vp1") is None

    metas = virtual_portfolio.list_virtual_portfolio_metadata()
    assert [(m.id, m.name) for m in metas] == [("vp2", "Two")]

    portfolios = virtual_portfolio.list_virtual_portfolios()
    assert [p.id for p in portfolios] == ["vp2"]
