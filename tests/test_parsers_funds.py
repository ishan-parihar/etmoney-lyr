"""Edge-case tests for fund parsers (detail, compare, featured, normalizers)."""

from pathlib import Path

import pytest

from etmoney_lyr.exceptions import UpstreamError
from etmoney_lyr.parsers.funds import (
    _num,
    normalize_listing,
    normalize_search,
    parse_amc_schemes,
    parse_compare,
    parse_featured,
    parse_fund_detail,
)

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def fund_html() -> str:
    return (FIX / "fund_detail.html").read_text()


@pytest.fixture(scope="module")
def parsed(fund_html) -> dict:
    return parse_fund_detail(fund_html)


class TestNum:
    @pytest.mark.parametrize(
        ("raw", "want"),
        [
            ("₹1,48,429 Cr", 148429 * 1e7),
            ("2.53%", 2.53),
            ("+0.13%", 0.13),
            ("-2.84%", -2.84),
            ("82.81", 82.81),
            (82.81, 82.81),
            (5, 5.0),
            ("947 Cr", 947e7),
            ("3.4 Lakh", 3.4e5),
            ("2K", 2000.0),
            ("1.5M", 1.5e6),
            (None, None),
            ("", None),
            ("N.A.", None),
            ("NA", None),
            ("$NaN", None),
            ("nan", None),
            ("Nil", None),
            ("-", None),
            ("no digits here", None),
        ],
    )
    def test_values(self, raw, want):
        got = _num(raw)
        if want is None:
            assert got is None
        else:
            assert got == pytest.approx(want)


class TestFundDetailReal:
    def test_identity(self, parsed):
        assert parsed["scheme_id"] == 19230
        assert "Parag Parikh Flexi Cap" in parsed["name"]
        assert parsed["riskometer"] == "Very High"

    def test_financials(self, parsed):
        assert parsed["aum"] == pytest.approx(148429e7)
        assert parsed["expense_ratio_total_pct"] == pytest.approx(1.29)
        assert parsed["expense_ratio_base_pct"] == pytest.approx(1.04)
        assert parsed["benchmark"] == "NIFTY 500 TRI"
        assert "NIFTY 500 TRI" in str(parsed["overview_raw"].get("Benchmark"))

    def test_trailing_returns_complete(self, parsed):
        rows = parsed["trailing_returns"]
        assert len(rows) == 10
        one_y = next(r for r in rows if r["period"] == "1 Year")
        assert one_y == {"period": "1 Year", "fund_pct": -2.02, "category_avg_pct": 1.58}

    def test_holdings_sorted_and_named(self, parsed):
        h = parsed["holdings"]
        assert len(h) == 85
        assert h[0]["name"] == "HDFC Bank Ltd."
        assert h[0]["pct"] == pytest.approx(7.55)
        pcts = [x["pct"] for x in h]
        assert pcts == sorted(pcts, reverse=True)

    def test_sectors_named(self, parsed):
        s = parsed["sectors"]
        assert len(s) == 18
        assert s[0]["name"] == "Financial"
        assert s[0]["pct"] == pytest.approx(25.69, abs=0.01)

    def test_managers(self, parsed):
        names = [m["name"] for m in parsed["managers"]]
        assert names == [
            "Raj Mehta",
            "Rajeev Thakkar",
            "Rukun Tarachandani",
            "Mansi Kariya",
            "Tejas Soman",
            "Aishwarya Dhar",
        ]
        assert all(len(m["bio"]) > 20 for m in parsed["managers"])

    def test_asset_allocation(self, parsed):
        aa = parsed["asset_allocation"]
        assert aa["equity_pct"] == pytest.approx(81.19)
        assert aa["debt_pct"] == pytest.approx(7.95)
        assert aa["other_pct"] == pytest.approx(10.86)
        assert aa["large_cap_pct"] == pytest.approx(74.0)
        assert aa["mid_cap_pct"] == pytest.approx(3.11)
        assert aa["small_cap_pct"] == pytest.approx(4.08)

    def test_peers(self, parsed):
        peers = parsed["peers"]
        assert len(peers) == 5
        by_id = {p["scheme_id"]: p for p in peers}
        motilal = by_id[25643]
        assert motilal["aum_cr"] == pytest.approx(13940.38, abs=0.1)
        assert motilal["sharpe"] is not None and motilal["sharpe"] > 0
        assert isinstance(motilal["returns_pct"], dict) and motilal["returns_pct"]

    def test_risk_ratios(self, parsed):
        fund_rr = parsed["risk_ratios_fund"]
        assert fund_rr and fund_rr["sharpeRatio"] == pytest.approx(0.76, abs=0.02)
        cat_rr = parsed["risk_ratios_category"]
        assert cat_rr and cat_rr["standardDeviation"] is not None

    def test_description_and_tax(self, parsed):
        assert "capital appreciation" in parsed["description"].lower()
        assert "20%" in parsed["stcg_tax"]
        assert "12.5%" in parsed["ltcg_tax"]


class TestFundDetailEdgeCases:
    def test_empty_page_raises(self):
        with pytest.raises(UpstreamError):
            parse_fund_detail("")

    def test_foreign_page_with_h1_only(self):
        # has an h1 so no raise; every optional section degrades to empty/None
        d = parse_fund_detail("<html><body><h1>Some Fund</h1></body></html>")
        assert d["name"] == "Some Fund"
        assert d["scheme_id"] is None
        assert d["trailing_returns"] == []
        assert d["holdings"] == []
        assert d["sectors"] == []
        assert d["managers"] == []
        assert d["peers"] == []
        assert d["aum"] is None
        assert all(v is None for v in d["asset_allocation"].values())

    def test_page_without_h1_or_dto_raises(self):
        with pytest.raises(UpstreamError):
            parse_fund_detail("<html><body>error</body></html>")

    def test_truncated_dto_tolerated(self):
        html = "<html><body><h1>F</h1><script>var compSchemeDTO = {broken</script></body></html>"
        d = parse_fund_detail(html)
        assert d["scheme_id"] is None


class TestCompare:
    def test_real_fixture(self):
        out = parse_compare((FIX / "compare.html").read_text())
        funds = out["funds"]
        assert len(funds) == 2
        pp = funds[0]
        assert pp["scheme_id"] == 19230
        assert pp["rating"] == 5
        assert pp["etm_rank"] == 9
        assert pp["min_sip"] == 3000
        assert pp["returns_pct"]["365"] == pytest.approx(-2.17)
        assert pp["sharpe"] is not None

    def test_missing_tiles_raises(self):
        with pytest.raises(UpstreamError):
            parse_compare("<html></html>")


class TestFeatured:
    def test_real_fixture(self):
        out = parse_featured((FIX / "featured.html").read_text())
        assert "Best SIP Funds" in out["title"]
        assert out["count"] >= 15
        f0 = out["funds"][0]
        assert set(f0) >= {"scheme_id", "slug", "name", "url"}
        ids = [f["scheme_id"] for f in out["funds"]]
        assert len(ids) == len(set(ids)), "duplicate scheme ids must be deduped"

    def test_empty_page(self):
        out = parse_featured("<html><body></body></html>")
        assert out["count"] == 0 and out["funds"] == []


class TestAmcSchemes:
    def test_valid(self):
        html = (
            '<script>var mfAmcSchemeDTO = [{"schemeId":1,"nameOfScheme":"A","categoryName":"Flexi Cap",'
            '"navValue":10.5,"schemeReturn":{"365":11.2}}];</script>'
        )
        out = parse_amc_schemes(html)
        assert out["count"] == 1
        assert out["schemes"][0]["returns_pct"] == {"365": 11.2}

    def test_missing_raises(self):
        with pytest.raises(UpstreamError):
            parse_amc_schemes("<html></html>")


class TestNormalizeListing:
    def test_real_payload(self):
        import json

        data = json.loads((FIX / "listing_api.json").read_text())
        norm = normalize_listing(data)
        assert norm["total"] == 1570
        assert norm["returned"] == 5
        f = norm["funds"][0]
        assert f["scheme_id"] == 42301
        assert f["amc"] == "Nippon India"
        assert f["group"] == "EQUITY"
        assert f["category"] == "International"
        assert f["nav"] == pytest.approx(33.686)
        assert f["returns_pct"]["365"] == pytest.approx(137.12)
        assert len(norm["categories"]) == 67
        assert any(c["group"] == "COMMODITIES" for c in norm["categories"])
        assert len(norm["amcs"]) == 43

    def test_empty_listing(self):
        norm = normalize_listing({"mfSchemeMiniList": [], "etmCategoryList": [], "amcMap": {}})
        assert norm["total"] is None
        assert norm["funds"] == []

    def test_null_rtn_fields_skipped(self):
        payload = {
            "totalSize": 1,
            "page_id": 0,
            "mfSchemeMiniList": [
                {
                    "sId": 1,
                    "parName": "X",
                    "rtnDet": {"365": 10.0, "30": None, "90": "bad"},
                    "rskratpoint": [None, "grey-text"],
                }
            ],
        }
        f = normalize_listing(payload)["funds"][0]
        assert f["returns_pct"] == {"365": 10.0}
        assert f["risk_label"] is None


class TestNormalizeSearch:
    def test_results(self):
        payload = {
            "totalCount": 2,
            "mfBasicDetailList": [
                {
                    "schemeId": 19230,
                    "nameOfScheme": "PPFCF Reg-G",
                    "parentName": "PPFCF",
                    "sdWebUrl": "/mutual-funds/ppfcf/19230",
                    "threeYearReturn": 13.6,
                },
                {"schemeId": 44196},
            ],
        }
        norm = normalize_search(payload)
        assert norm["total"] == 2
        r0 = norm["results"][0]
        assert r0["scheme_id"] == 19230 and r0["3y_return_pct"] == 13.6

    def test_zero_results(self):
        norm = normalize_search({"totalCount": 0, "mfBasicDetailList": []})
        assert norm["total"] == 0 and norm["results"] == []
