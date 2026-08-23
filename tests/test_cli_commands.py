"""CLI command-handler tests with the HTTP boundary faked at class level."""

import json

import pytest

from etmoney_lyr.cli_main import main
from tests.test_mcp_integration import FakeClient


@pytest.fixture
def fake_upstream(monkeypatch):
    from pathlib import Path

    from etmoney_lyr.client import EtMoneyClient

    fx = Path(__file__).parent / "fixtures"
    fake = FakeClient(
        routes={
            "SEARCH": None,
            "LIST": {
                "totalSize": 1,
                "page_id": 0,
                "mfSchemeMiniList": [],
                "etmCategoryList": [],
                "amcMap": {},
            },
        }
    )

    async def search(self, term):
        return {
            "totalCount": 1,
            "mfBasicDetailList": [
                {
                    "schemeId": 6558,
                    "nameOfScheme": "HDFC Small Cap Reg-G",
                    "parentName": "HDFC Small Cap",
                }
            ],
        }

    async def listing(self, **params):
        return {
            "totalSize": 26,
            "page_id": params.get("page", 0),
            "amcMap": {},
            "etmCategoryList": [
                {"id": 129, "primary": "COMMODITIES", "secondary": "GOLD", "name": "GOLD"},
                {"id": 79, "primary": "EQUITY", "secondary": "FLEXI CAP", "name": "X"},
            ],
            "mfSchemeMiniList": [
                {
                    "sId": 12760,
                    "parName": "SBI Gold",
                    "name": "SBI Gold-Growth",
                    "amcName": "SBI",
                    "pCat": "COMMODITIES",
                    "catDispName": "Gold",
                    "etmCat": 129,
                    "sdWebUrl": "/mutual-funds/sbi-gold/12760",
                    "lNv": 46.31,
                    "lNvD": {"value": "21/08/2026"},
                    "expRat": 0.42,
                    "asSz": 15811.0,
                    "assetSizeFor": "15,812 Cr",
                    "etmRnk": -1,
                    "rskratpoint": ["Low"],
                    "lockinDays": 0,
                    "isD": False,
                    "isBuyable": True,
                    "rtnDet": {"365": 25.0},
                }
            ],
        }

    async def html(self, path, params=None):
        if "compare" in path:
            return (fx / "compare.html").read_text()
        if "featured/" in path:
            return (fx / "featured.html").read_text()
        if "2705" in path or "hdfc-bank-ltd" in path:
            return (fx / "hdfc.html").read_text()
        if "/stocks/" in path:
            return (fx / "gainers.html").read_text()
        return (fx / "fund_detail.html").read_text()

    monkeypatch.setattr(EtMoneyClient, "search_funds_raw", search)
    monkeypatch.setattr(EtMoneyClient, "fund_listing_raw", listing)
    monkeypatch.setattr(EtMoneyClient, "get_html", html)
    return fake


class TestSearchCmd:
    def test_toon_output(self, fake_upstream, capsys):
        main(["search", "hdfc small cap"])
        out = capsys.readouterr().out
        assert "total: 1" in out and "scheme_id: 6558" in out

    def test_json_output(self, fake_upstream, capsys):
        main(["--json", "search", "x"])
        data = json.loads(capsys.readouterr().out)
        assert data["results"][0]["scheme_id"] == 6558

    def test_empty_results_hint(self, monkeypatch, capsys):
        from etmoney_lyr.client import EtMoneyClient

        async def empty(self, term):
            return {"totalCount": 0, "mfBasicDetailList": []}

        monkeypatch.setattr(EtMoneyClient, "search_funds_raw", empty)
        main(["search", "zzzz"])
        out = capsys.readouterr().out
        assert "none" in out and "help:" in out


class TestFundsCmd:
    def test_meta_then_rows(self, fake_upstream, capsys):
        main(["funds", "--category", "gold", "--size", "3"])
        out = capsys.readouterr().out
        assert "showing: 1" in out or "total: 26" in out
        assert "SBI Gold" in out

    def test_bad_category_exits_2(self, fake_upstream, capsys):
        with pytest.raises(SystemExit) as e:
            main(["funds", "--category", "nope"])
        assert e.value.code == 2


class TestFundCmd:
    def test_core_view(self, fake_upstream, capsys):
        main(["fund", "19230"])
        out = capsys.readouterr().out
        assert "Parag Parikh Flexi Cap" in out
        assert "holdings_count: 85" in out
        assert "--full" in out  # disclosure hint

    def test_full_view(self, fake_upstream, capsys):
        main(["fund", "19230", "--full"])
        out = capsys.readouterr().out
        assert "trailing_returns" in out and "managers" in out


class TestCompareCmd:
    def test_two_ids(self, fake_upstream, capsys):
        main(["compare", "19230,25643"])
        out = capsys.readouterr().out
        assert "Motilal Oswal Flexi Cap" in out


class TestStocksAndListingCmds:
    def test_stocks_screen(self, fake_upstream, capsys):
        main(["stocks", "top_gainers", "--limit", "2"])
        out = capsys.readouterr().out
        assert "screen: top_gainers" in out
        assert "Welspun Corp Ltd." in out

    def test_index(self, fake_upstream, capsys):
        main(["index", "nifty_50", "--limit", "2"])
        out = capsys.readouterr().out
        assert "count: 224" in out or "count: 2" in out

    def test_sector(self, fake_upstream, capsys):
        main(["sector", "banking", "--limit", "1"])
        out = capsys.readouterr().out
        assert "sector: banking" in out

    def test_stock_detail(self, fake_upstream, capsys):
        main(["stock", "2705"])
        out = capsys.readouterr().out
        assert "HDFC Bank Ltd." in out

    def test_stock_detail_full(self, fake_upstream, capsys):
        main(["stock", "2705", "--full"])
        out = capsys.readouterr().out
        assert "returns_pct" in out


class TestFeaturedAndCategories:
    def test_featured(self, fake_upstream, capsys):
        main(["featured", "best_sip_funds"])
        out = capsys.readouterr().out
        assert "Best SIP Funds" in out

    def test_featured_unknown_exits_2(self, fake_upstream, capsys):
        with pytest.raises(SystemExit) as e:
            main(["featured", "bogus"])
        assert e.value.code == 2

    def test_categories(self, fake_upstream, capsys):
        main(["categories"])
        out = capsys.readouterr().out
        # upstream returns empty category list here; must still render cleanly
        assert "total_categories" in out or "groups" in out


class TestStatus:
    def test_status_reachable(self, monkeypatch, capsys):
        from etmoney_lyr.client import EtMoneyClient

        async def ok(self, path, params=None):
            class R:
                status_code = 200

            return R()

        monkeypatch.setattr(EtMoneyClient, "request", ok)
        main(["status"])
        out = capsys.readouterr().out
        assert "upstream_reachable" in out

    def test_status_down(self, monkeypatch, capsys):
        from etmoney_lyr.client import EtMoneyClient
        from etmoney_lyr.exceptions import UpstreamError

        async def down(self, path, params=None):
            raise UpstreamError("connection refused")

        monkeypatch.setattr(EtMoneyClient, "request", down)
        main(["status"])
        out = capsys.readouterr().out
        assert "unreachable" in out and "connection refused" in out


class TestEmitTruncation:
    def test_long_lists_truncated_with_marker(self, capsys):
        from etmoney_lyr.cli_main import _emit

        _emit({"rows": [{"i": i} for i in range(30)]}, False)
        out = capsys.readouterr().out
        assert "[30 items]" in out and "(10 more)" in out

    def test_scalar_list_inline(self, capsys):
        from etmoney_lyr.cli_main import _emit

        _emit({"tags": ["a", "b"]}, False)
        out = capsys.readouterr().out
        assert 'tags: "a, b"' in out  # comma forces TOON quoting

    def test_json_passthrough(self, capsys):
        from etmoney_lyr.cli_main import _emit

        _emit({"a": 1}, True)
        assert json.loads(capsys.readouterr().out) == {"a": 1}
