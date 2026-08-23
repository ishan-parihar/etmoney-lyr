"""Full-stack integration tests: FastMCP in-memory client drives the real server.

Exercises schema generation, argument validation, serialization, and the
complete registration path — with the HTTP boundary faked at the
EtMoneyClient class level.
"""

import json

import pytest
from fastmcp import Client

from etmoney_lyr.server import create_mcp_server


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text
        self.status_code = 200
        self.is_error = False

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    """Routes fake upstream responses by path prefix."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.calls: list[str] = []

    def _match(self, path: str):
        for prefix, payload in self.routes.items():
            if path.startswith(prefix):
                self.calls.append(path)
                return payload
        raise AssertionError(f"unexpected upstream path {path}")

    async def search_funds_raw(self, term: str):
        self.calls.append(("SEARCH", term))
        return {"totalCount": 1, "mfBasicDetailList": [{"schemeId": 19230}]}

    async def fund_listing_raw(self, **params):
        p = self._match("LIST")
        import json as _json

        return _json.loads(_json.dumps(p))  # deep copy

    async def get_html(self, path: str, params=None):
        from pathlib import Path

        fx = Path(__file__).parent / "fixtures"
        self.calls.append(("HTML", path))
        if "compare" in path:
            return (fx / "compare.html").read_text()
        if "featured/" in path:
            return (fx / "featured.html").read_text()
        if "hdfc-bank-ltd" in path:
            return (fx / "hdfc.html").read_text()
        if "/mutual-funds/" in path:
            return (fx / "fund_detail.html").read_text()
        if "/stocks/" in path:
            return (fx / "gainers.html").read_text()
        raise AssertionError(f"unexpected html path {path}")

    async def aclose(self):
        pass


def install_fake(monkeypatch, routes):
    from etmoney_lyr.client import EtMoneyClient
    from etmoney_lyr.tools import funds as funds_mod
    from etmoney_lyr.tools import stocks as stocks_mod

    fake = FakeClient(routes)
    # patch at the source so both tools modules and lazily-imported clients see it
    monkeypatch.setattr(funds_mod, "get_client", lambda: fake)
    monkeypatch.setattr(stocks_mod, "get_client", lambda: fake)
    monkeypatch.setattr(EtMoneyClient, "search_funds_raw", FakeClient.search_funds_raw)
    monkeypatch.setattr(EtMoneyClient, "fund_listing_raw", FakeClient.fund_listing_raw)
    monkeypatch.setattr(EtMoneyClient, "get_html", FakeClient.get_html)
    return fake


@pytest.fixture
async def mcp_client(monkeypatch):
    install_fake(
        monkeypatch,
        routes={
            "SEARCH": None,
            "LIST": {
                "totalSize": 2,
                "page_id": 0,
                "amcMap": {"20": "Nippon India"},
                "etmCategoryList": [
                    {"id": 79, "primary": "EQUITY", "secondary": "FLEXI CAP", "name": "X"},
                    {"id": 129, "primary": "COMMODITIES", "secondary": "GOLD", "name": "Y"},
                ],
                "mfSchemeMiniList": [
                    {
                        "sId": 42301,
                        "parName": "Taiwan Fund",
                        "name": "Taiwan Fund Reg-G",
                        "amcName": "Nippon India",
                        "aId": 20,
                        "pCat": "EQUITY",
                        "catDispName": "International",
                        "etmCat": 50,
                        "sdWebUrl": "/mutual-funds/t/42301",
                        "lNv": 33.6,
                        "lNvD": {"value": "21/08/2026"},
                        "expRat": 2.53,
                        "asSz": 947.0,
                        "assetSizeFor": "947 Cr",
                        "etmRnk": -1,
                        "rskratpoint": ["Not Rated"],
                        "lockinDays": 0,
                        "isD": False,
                        "isBuyable": True,
                        "rtnDet": {"365": 137.0},
                    }
                ],
            },
        },
    )
    server = create_mcp_server()
    async with Client(server) as c:
        yield c


async def _call(client, name, args):
    res = await client.call_tool(name, args)
    text = res.content[0].text
    return json.loads(text)


class TestProtocolLayer:
    async def test_list_tools_returns_all_ten(self, mcp_client):
        tools = await mcp_client.list_tools()
        assert len(tools) == 10
        names = {t.name for t in tools}
        assert "mf_search" in names and "stock_detail" in names

    async def test_tool_schemas_have_descriptions(self, mcp_client):
        tools = await mcp_client.list_tools()
        for t in tools:
            assert t.description, f"{t.name} missing description"
            assert t.inputSchema.get("type") == "object"


class TestToolCallsThroughProtocol:
    async def test_mf_search(self, mcp_client):
        out = await _call(mcp_client, "mf_search", {"query": "parag"})
        assert out["ok"] is True and out["results"][0]["scheme_id"] == 19230

    async def test_mf_list_with_category_name(self, mcp_client):
        out = await _call(mcp_client, "mf_list", {"category": "gold", "size": 5})
        assert out["ok"] is True
        assert out["category_filter_applied"]["resolved_id"] == 129
        assert out["funds"][0]["scheme_id"] == 42301

    async def test_mf_list_group_filter(self, mcp_client):
        out = await _call(mcp_client, "mf_list", {"group": "COMMODITIES"})
        assert out["ok"] is True and out["total"] == 2

    async def test_mf_categories(self, mcp_client):
        out = await _call(mcp_client, "mf_categories", {})
        assert out["groups"]["EQUITY"] == 1
        assert out["groups"]["COMMODITIES"] == 1

    async def test_mf_detail_full_report(self, mcp_client):
        out = await _call(mcp_client, "mf_detail", {"scheme_id": 19230})
        assert out["ok"] is True
        assert out["aum"] == pytest.approx(148429e7)
        assert len(out["holdings"]) == 85

    async def test_mf_compare(self, mcp_client):
        out = await _call(mcp_client, "mf_compare", {"scheme_ids": [19230, 25643]})
        assert out["ok"] is True and len(out["funds"]) == 2

    async def test_mf_featured(self, mcp_client):
        out = await _call(mcp_client, "mf_featured", {"theme": "best_sip_funds"})
        assert out["ok"] is True and out["count"] >= 15

    async def test_stock_screen(self, mcp_client):
        out = await _call(mcp_client, "stock_screen", {"screen": "top_gainers", "limit": 3})
        assert out["ok"] is True
        assert out["screen"] == "top_gainers"
        assert len(out["stocks"]) == 3

    async def test_index_stocks(self, mcp_client):
        out = await _call(mcp_client, "index_stocks", {"index": "nifty_50", "limit": 2})
        assert out["ok"] is True and len(out["stocks"]) == 2

    async def test_sector_stocks(self, mcp_client):
        out = await _call(mcp_client, "sector_stocks", {"sector": "banking", "limit": 2})
        assert out["ok"] is True and out["sector"] == "banking"

    async def test_stock_detail_via_url_ref(self, mcp_client):
        out = await _call(mcp_client, "stock_detail", {"stock_ref": "/stocks/hdfc-bank-ltd/2705"})
        assert out["ok"] is True
        assert out["name"] == "HDFC Bank Ltd."


class TestErrorContractThroughProtocol:
    async def test_validation_errors_are_structured_not_exceptions(self, mcp_client):
        out = await _call(mcp_client, "mf_compare", {"scheme_ids": [1]})
        assert out["ok"] is False and out["error"] == "validation"

    async def test_unknown_category_is_structured(self, mcp_client):
        out = await _call(mcp_client, "mf_list", {"category": "zzz"})
        assert out["ok"] is False and out["error"] == "validation"

    async def test_short_query_structured(self, mcp_client):
        out = await _call(mcp_client, "mf_search", {"query": "x"})
        assert out["ok"] is False and out["error"] == "validation"
