"""Tool-level tests: validation paths without network + error mapping."""

import pytest

from etmoney_lyr.exceptions import NotFoundError, UpstreamError, ValidationError
from etmoney_lyr.tools.common import handle_api_error
from etmoney_lyr.tools.funds import (
    _resolve_category,
    mf_compare,
    mf_detail,
    mf_featured,
    mf_list,
    mf_search,
)
from etmoney_lyr.tools.stocks import stock_detail

CATS = [
    {"id": 79, "group": "EQUITY", "display": "FLEXI CAP", "name": "EQUITY_FLEXI_CAP"},
    {"id": 57, "group": "DEBT", "display": "LIQUID", "name": "DEBT_LIQUID"},
    {"id": 129, "group": "COMMODITIES", "display": "GOLD", "name": "GOLD"},
]


class TestResolveCategory:
    def test_numeric_string(self):
        assert _resolve_category("79", CATS) == 79

    def test_exact_display_case_insensitive(self):
        assert _resolve_category("flexi cap", CATS) == 79
        assert _resolve_category("GOLD", CATS) == 129

    def test_none_and_empty(self):
        assert _resolve_category(None, CATS) is None
        assert _resolve_category("", CATS) is None

    def test_unique_substring(self):
        assert _resolve_category("flexi", CATS) == 79

    def test_ambiguous_substring_raises(self):
        with pytest.raises(ValidationError):
            _resolve_category("l", CATS)

    def test_unknown_raises_with_hint(self):
        with pytest.raises(ValidationError, match="unknown category"):
            try:
                _resolve_category("nope", CATS)
            except ValidationError as e:
                assert "mf_categories" in (e.hint or "")
                raise


class TestErrorMapping:
    def test_not_found(self):
        out = handle_api_error(NotFoundError("gone", hint="h"))
        assert out == {"ok": False, "error": "not_found", "message": "gone", "hint": "h"}

    def test_upstream(self):
        out = handle_api_error(UpstreamError("bad"))
        assert out["error"] == "upstream_error" and out["hint"] is None

    def test_unexpected_reraises(self):
        with pytest.raises(KeyError):
            handle_api_error(KeyError("boom"))


class TestValidationNoNetwork:
    async def test_search_short_query(self):
        out = await mf_search("a")
        assert out["ok"] is False and out["error"] == "validation"

    async def test_compare_needs_two_ids(self):
        out = await mf_compare([19230])
        assert out["ok"] is False and out["error"] == "validation"

    async def test_compare_max_four(self):
        out = await mf_compare([1, 2, 3, 4, 5])
        assert out["ok"] is False and "at most 4" in out["message"]

    async def test_compare_rejects_duplicate_ids(self):
        out = await mf_compare([19230, 19230])
        assert out["ok"] is False and "duplicate" in out["message"]

    async def test_compare_non_numeric_id(self):
        out = await mf_compare(["abc", 2])
        assert out["ok"] is False and out["error"] == "validation"

    async def test_featured_unknown_theme(self):
        out = await mf_featured("does-not-exist")
        assert out["ok"] is False
        assert "best_sip_funds" in (out.get("hint") or "")

    async def test_featured_normalizes_input(self, monkeypatch):
        captured = {}

        async def fake_get_html(path, params=None):
            captured["path"] = path
            return "<html><body><h1>t</h1></body></html>"

        from etmoney_lyr.tools import funds as funds_mod

        class FakeClient:
            get_html = staticmethod(fake_get_html)

        monkeypatch.setattr(funds_mod, "get_client", lambda: FakeClient())
        out = await mf_featured("Best-SIP Funds")
        assert out["theme"] == "best_sip_funds"
        assert "best-sip-funds" in captured["path"]

    async def test_list_rejects_bad_size(self, monkeypatch):
        from etmoney_lyr.tools import funds as funds_mod

        async def fake_cats():
            return CATS

        monkeypatch.setattr(funds_mod, "_categories_from_upstream", fake_cats)
        out = await mf_list(size=99)
        assert out["ok"] is False and "size must be" in out["message"]
        out = await mf_list(page=-1)
        assert out["ok"] is False and "page" in out["message"]

    async def test_list_unknown_category_returns_structured_error(self, monkeypatch):
        from etmoney_lyr.tools import funds as funds_mod

        async def fake_cats():
            return CATS

        monkeypatch.setattr(funds_mod, "_categories_from_upstream", fake_cats)
        out = await mf_list(category="zzz")
        assert out["ok"] is False and out["error"] == "validation"
        assert "mf_categories" in (out.get("hint") or "")

    async def test_stock_detail_invalid_ref(self):
        out = await stock_detail("../etc/passwd")
        assert out["ok"] is False and out["error"] == "validation"

    async def test_stock_detail_accepts_url_path(self, monkeypatch):
        from etmoney_lyr.tools import stocks as stocks_mod

        captured = {}

        async def fake_get_html(path, params=None):
            captured["path"] = path
            return "<html></html>"

        class FakeClient:
            get_html = staticmethod(fake_get_html)

        monkeypatch.setattr(stocks_mod, "get_client", lambda: FakeClient())
        await stock_detail("/stocks/hdfc-bank-ltd/2705")
        assert captured["path"] == "/stocks/hdfc-bank-ltd/2705"


class TestNetworkErrorPassthrough:
    async def test_upstream_error_becomes_structured(self, monkeypatch):
        from etmoney_lyr.tools import funds as funds_mod

        async def boom(*a, **k):
            raise UpstreamError("upstream down")

        monkeypatch.setattr(
            funds_mod, "get_client", lambda: type("C", (), {"search_funds_raw": boom})()
        )
        out = await mf_search("valid query")
        assert out == {
            "ok": False,
            "error": "upstream_error",
            "message": "upstream down",
            "hint": None,
        }

    async def test_not_found_passthrough(self, monkeypatch):
        from etmoney_lyr.tools import funds as funds_mod

        async def boom(*a, **k):
            raise NotFoundError("missing fund")

        monkeypatch.setattr(funds_mod, "get_client", lambda: type("C", (), {"get_html": boom})())
        out = await mf_detail(99999999)
        assert out["error"] == "not_found"
