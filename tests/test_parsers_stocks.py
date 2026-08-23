"""Edge-case tests for stock parsers (RSC-based)."""

from pathlib import Path

import pytest

from etmoney_lyr.exceptions import UpstreamError
from etmoney_lyr.parsers.stocks import parse_stock_detail, parse_stock_list

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def gainers():
    return parse_stock_list((FIX / "gainers.html").read_text())


@pytest.fixture(scope="module")
def hdfc():
    return parse_stock_detail((FIX / "hdfc.html").read_text())


class TestStockList:
    def test_title_and_count(self, gainers):
        assert "Top Gainers" in gainers["title"]
        assert gainers["count"] == 224

    def test_first_row_fields(self, gainers):
        s = gainers["stocks"][0]
        assert s["name"] == "Welspun Corp Ltd."
        assert s["price"] == pytest.approx(2311.9)
        assert s["return_1d_pct"] == pytest.approx(15.3)
        assert s["market_cap_bucket"] == "Mid Cap"
        assert s["industry"] is not None
        assert s["url"].startswith("/stocks/")

    def test_rows_sorted_by_gain_desc(self, gainers):
        rets = [s["return_1d_pct"] for s in gainers["stocks"]]
        assert rets == sorted(rets, reverse=True)

    def test_all_ids_unique(self, gainers):
        ids = [s["stock_id"] for s in gainers["stocks"]]
        assert len(ids) == len(set(ids))

    def test_no_rsc_payload_raises(self):
        with pytest.raises(UpstreamError):
            parse_stock_list("<html><body>plain page</body></html>")

    def test_rsc_without_stocklist_raises(self):
        with pytest.raises(UpstreamError):
            parse_stock_list('<script>self.__next_f.push([1,"{\\"a\\":1}"])</script>')

    def test_null_price_tolerated(self):
        html = (
            '<script>self.__next_f.push([1,"'
            + '{"pageName":"X","stockList":[{"stockId":1,"displayName":"A","currPrice":null,'
            '"prevClose":5.0,"returnPerc1D":"$NaN"}]}'.replace('"', '\\"')
            + '"])</script>'
        )
        out = parse_stock_list(html)
        s = out["stocks"][0]
        assert s["price"] is None
        assert s["return_1d_pct"] is None  # "$NaN" → None
        assert s["prev_close"] == pytest.approx(5.0)

    def test_non_dict_rows_skipped(self):
        inner = '{"stockList":[42,null,{"stockId":2,"displayName":"B"}]}'
        esc = inner.replace('"', '\\"')
        out = parse_stock_list(f'<script>self.__next_f.push([1,"{esc}"])</script>')
        assert [s["name"] for s in out["stocks"]] == ["B"]

    def test_empty_list(self):
        inner = '{"pageName":"Empty screen","stockList":[]}'
        esc = inner.replace('"', '\\"')
        out = parse_stock_list(f'<script>self.__next_f.push([1,"{esc}"])</script>')
        assert out["count"] == 0 and out["stocks"] == []


class TestStockDetail:
    def test_identity_and_quote(self, hdfc):
        assert hdfc["name"] == "HDFC Bank Ltd."
        assert hdfc["scrip"] == "HDFCBANK"
        assert hdfc["price"] == pytest.approx(726.95)
        assert hdfc["delta_pct"] == pytest.approx(0.26)

    def test_returns_complete(self, hdfc):
        r = hdfc["returns_pct"]
        assert set(r) == {"1w", "1m", "3m", "6m", "1y", "3y", "5y", "10y", "15y"}
        assert r["1y"] == pytest.approx(-26.98)
        assert r["15y"] == pytest.approx(530.98)

    def test_about_text(self, hdfc):
        assert hdfc["about"].startswith("The company was established")

    def test_peer_fundamentals(self, hdfc):
        peers = hdfc["fundamentals_peers"]
        assert len(peers) == 3
        names = {p["name"] for p in peers}
        assert {"HDFC Bank Ltd.", "ICICI Bank Ltd.", "State Bank of India"} <= names
        top = peers[0]
        assert top["ltp"] == pytest.approx(726.95)
        assert top["roe_pct"] == "14.41"

    def test_scores_present(self, hdfc):
        assert hdfc["upside_potential_score"] == 3
        assert hdfc["financial_strength_score"] == 4

    def test_missing_company_block_raises(self):
        with pytest.raises(UpstreamError):
            parse_stock_detail('<script>self.__next_f.push([1,"{\\"unrelated\\":true}"])</script>')


class TestCrossScreenConsistency:
    """Every screen/index/sector URL must produce the same row schema."""

    @pytest.mark.parametrize("field", ["stock_id", "name", "price", "return_1d_pct", "url"])
    def test_row_has_core_fields(self, gainers, field):
        assert all(field in s for s in gainers["stocks"])
