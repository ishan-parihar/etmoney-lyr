"""Parsers for mutual-fund pages: detail report card, compare, featured listings.

Pure functions: raw HTML in → plain dicts out. No I/O, no client.
"""

import json
import re

from bs4 import BeautifulSoup

from etmoney_lyr.exceptions import UpstreamError
from etmoney_lyr.jsvars import find_key, parse_js_var


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\u20b9", "₹").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def _as_dict(obj) -> dict:
    return obj if isinstance(obj, dict) else {}


def _as_list(obj) -> list:
    return obj if isinstance(obj, list) else []


def _num(value) -> float | None:
    """Parse '1,48,429 Cr' / '2.53%' / '+0.13%' style values into floats.

    Suffix multipliers: K=1e3, L/Lakh=1e5, M=1e6, Cr/Crore=1e7.
    Returns None for N.A./empty/None.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() in {"n.a.", "na", "-", "$nan", "nan", "nil"}:
        return None
    m = re.search(r"-?[\d,]+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        num = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    # Suffix multiplier read directly after the numeric token ("Cr", "Lakh",
    # "K", "M") — case-insensitive, whitespace-tolerant.
    rest = s[m.end() :].lstrip(" ").lower()
    if rest.startswith(("crore", "cr")):
        num *= 1e7
    elif rest.startswith(("lakh", "l")):
        num *= 1e5
    elif rest.startswith("k"):
        num *= 1e3
    elif rest.startswith("m"):
        num *= 1e6
    return num


# ── fund detail page ────────────────────────────────────────────────────────


def _parse_overview_table(soup) -> dict[str, str]:
    out: dict[str, str] = {}
    for strong in soup.select("strong.mfSceme-key-title"):
        td = strong.find_parent("td")
        row = td.find_next_sibling("td") if td else None
        if row:
            # keep only the main value; drop nested help-text tables
            for extra in row.select("table"):
                extra.decompose()
            key = _clean(strong.get_text())
            val = _clean(row.get_text(" "))
            if key:
                out[key] = val
    return out


def _parse_trailing_returns(soup) -> list[dict]:
    """Find the trailing-returns table via its header cells."""
    for table in soup.find_all("table"):
        headers = [_clean(th.get_text()) for th in table.find_all("th")]
        if headers[:2] == ["Period", "This fund"]:
            rows = []
            for tr in table.find_all("tr"):
                cells = [_clean(td.get_text()) for td in tr.find_all("td")]
                if len(cells) == 3 and cells[0] != "Period":
                    rows.append(
                        {
                            "period": cells[0],
                            "fund_pct": _num(cells[1]),
                            "category_avg_pct": _num(cells[2]),
                        }
                    )
            return rows
    return []


def _parse_asset_allocation(html: str) -> dict:
    """Percent labels (Equity 81.19% / Large Cap 74%) live in sibling sections of
    the heading; match on the distinctive label+percent pairs across the page."""
    text = _clean(re.sub(r"<[^>]+>", " ", html))
    out: dict = {}
    for label, key in [
        ("Equity", "equity_pct"),
        ("Debt", "debt_pct"),
        ("Other", "other_pct"),
        ("Large Cap", "large_cap_pct"),
        ("Mid Cap", "mid_cap_pct"),
        ("Small Cap", "small_cap_pct"),
        ("Other Cap", "other_cap_pct"),
    ]:
        m = re.search(label + r"\s*\|?\s*(-?[\d.]+)%", text)
        # first match wins; asset-allocation block appears before any other
        out[key] = float(m.group(1)) if m else None
    return out


def _parse_holdings(allocation: dict, company_map: dict) -> list[dict]:
    """companyAllocationData + mfCompanyDTOMapJson → named holdings."""
    holdings: list[dict] = []
    buckets = allocation if isinstance(allocation, dict) else {}
    for bucket_name, entries in buckets.items():
        weight_by_id = entries if isinstance(entries, dict) else {}
        for cid, pct in weight_by_id.items():
            info = (company_map or {}).get(str(cid)) or {}
            holdings.append(
                {
                    "name": info.get("company") or f"company:{cid}",
                    "bucket": bucket_name,
                    "pct": pct,
                    "stock_url": info.get("stockUrl"),
                }
            )
    holdings.sort(key=lambda h: -(h["pct"] or 0))
    return holdings


def _parse_sectors(alloc: dict, sector_map: dict) -> list[dict]:
    """sectorAllocationData is bucketed {GROUP: {sector_id: pct}} like holdings."""
    sectors: list[dict] = []
    for _bucket, entries in (alloc or {}).items():
        if not isinstance(entries, dict):
            continue
        for sid, pct in entries.items():
            info = (sector_map or {}).get(str(sid)) or {}
            sectors.append({"name": info.get("sector") or f"sector:{sid}", "pct": pct})
    sectors.sort(key=lambda s: -(s["pct"] or 0))
    return sectors


def _parse_managers(soup) -> list[dict]:
    """Accordion structure: .accordion-item-header = name, body content = bio."""
    managers: list[dict] = []
    for item in soup.select(".fund-manager-accordian .accordion-item"):
        header = item.select_one(".accordion-item-header")
        if not header:
            continue
        name = _clean(header.get_text())
        body = item.select_one(".accordion-item-body-content")
        managers.append({"name": name, "bio": _clean(body.get_text(" "))[:400] if body else ""})
    return managers


def parse_fund_detail(html: str) -> dict:
    """Full report card for a scheme page. Raises UpstreamError on empty/foreign page."""
    soup = BeautifulSoup(html, "lxml")
    current = _as_dict(_as_dict(parse_js_var(html, "compSchemeDTO")).get("currentSchemeDto"))
    if not current and not soup.select_one("h1"):
        raise UpstreamError("unrecognized fund detail page (no DTO, no title)")

    peers_raw = _as_list(parse_js_var(html, "mfPeerSchemesDTO"))
    peer_card = _as_dict(parse_js_var(html, "peerReportCardData"))
    category_card = _as_dict(parse_js_var(html, "mfcategoryReportCardDataDTO"))
    company_alloc = _as_dict(parse_js_var(html, "companyAllocationData"))
    company_map = _as_dict(parse_js_var(html, "mfCompanyDTOMapJson"))
    sector_alloc = _as_dict(parse_js_var(html, "sectorAllocationData"))
    sector_map = _as_dict(parse_js_var(html, "mfSectorDTOMapJson"))

    overview = _parse_overview_table(soup)

    def ov(key: str) -> str:
        return overview.get(key, "")

    result: dict = {
        "scheme_id": current.get("schemeId"),
        "name": current.get("nameOfScheme") or _clean(soup.h1.get_text() if soup.h1 else ""),
        "parent_name": current.get("parentDisplayName"),
        "category_id": current.get("categoryId"),
        "is_direct": current.get("isDirect"),
        "fund_option": current.get("fundOption"),
        "fund_type": current.get("fundType"),
        "riskometer": current.get("riskometer") or ov("Risk"),
        "description": _clean(current.get("parentSchemeDesc") or ""),
        "counterpart_scheme_id": current.get("dirSchemeId")
        if current.get("isDirect")
        else current.get("regSchemeId"),
        "sid_url": current.get("sidUrl"),
        "overview_raw": overview,
        "aum": _num(ov("AUM (Fund size)")),
        "exit_load": ov("Exit load"),
        "lock_in": ov("Lock-in Period"),
        "age": ov("Age"),
        "benchmark": ov("Benchmark"),
        "min_investment": ov("Min. investment"),
        "expense_ratio_base_pct": _num(ov("Base Expense ratio")),
        "expense_ratio_total_pct": _num(ov("Total Expense ratio")),
        "etm_rating": _num(ov("ET Money Rating")),
        "stcg_tax": ov("Short term capital gains (STCG)"),
        "ltcg_tax": ov("Long term capital gains (LTCG)"),
        "asset_allocation": _parse_asset_allocation(html),
        "holdings": _parse_holdings(company_alloc, company_map),
        "sectors": _parse_sectors(sector_alloc, sector_map),
        "managers": _parse_managers(soup),
        "trailing_returns": _parse_trailing_returns(soup),
        "risk_ratios_fund": peer_card.get(str(current.get("schemeId")))
        or (peer_card.get(current.get("schemeId")) if isinstance(peer_card, dict) else None),
        "risk_ratios_category": category_card or None,
    }

    # Peer comparison: mfPeerSchemesDTO includes the current fund itself.
    peer_rows = []
    for p in peers_raw:
        if not isinstance(p, dict):
            continue
        rets = p.get("lumpsumReturns") or {}
        card = p.get("mfReportCardData") or {}
        start = p.get("fundStartDate") or {}
        peer_rows.append(
            {
                "scheme_id": p.get("schemeId"),
                "name": p.get("parentSchemeName") or p.get("nameOfScheme"),
                "rank": p.get("rank"),
                "rank_out_of": p.get("outOfRank"),
                "aum_cr": p.get("assetSize"),
                "expense_ratio_pct": p.get("expenseRatio"),
                "start_date": start.get("value") if isinstance(start, dict) else None,
                "returns_pct": {k: v for k, v in rets.items() if isinstance(v, (int, float))},
                "std_dev": card.get("standardDeviation"),
                "sharpe": card.get("sharpeRatio"),
                "alpha": card.get("alpha"),
                "beta": card.get("beta"),
                "sortino": card.get("sortinoRatio"),
            }
        )
    result["peers"] = peer_rows
    return result


# ── compare page ────────────────────────────────────────────────────────────


def parse_compare(html: str) -> dict:
    """Compare page: schemeComparisionTileDtoList holds one tile per scheme."""
    tiles = parse_js_var(html, "schemeComparisionTileDtoList")
    if not isinstance(tiles, list):
        raise UpstreamError(
            "compare data missing — page may require ≥2 valid scheme ids",
            hint="use /mutual-funds/<slug>/<id> URLs to find ids first",
        )
    funds = []
    for t in _as_list(tiles):
        if not isinstance(t, dict):
            continue
        rets = t.get("mfReturnDetails") or {}
        card = t.get("mfReportCardData") or {}
        start = t.get("fundStartDate") or {}
        funds.append(
            {
                "scheme_id": t.get("schemeId"),
                "name": t.get("nameOfScheme"),
                "rating": t.get("rating"),
                "etm_rank": t.get("etmRank"),
                "consistency_rating": t.get("consistencyRating"),
                "aum_cr": t.get("aumSize"),
                "amc_aum_cr": t.get("aumSize"),
                "expense_ratio_pct": t.get("expenseRatio"),
                "exit_load": t.get("exitLoad"),
                "primary_category": t.get("primaryCategory"),
                "secondary_category": t.get("secondaryCategory"),
                "risk_grade": t.get("riskGrade"),
                "benchmark_index": t.get("benchmarkIndex"),
                "min_lumpsum": t.get("minLsInvestment"),
                "min_sip": t.get("minSIPInvestment"),
                "lock_in_days": t.get("lockInDays"),
                "start_date": start.get("value") if isinstance(start, dict) else None,
                "returns_pct": {k: v for k, v in rets.items() if isinstance(v, (int, float))},
                "std_dev": card.get("standardDeviation"),
                "sharpe": card.get("sharpeRatio"),
                "alpha": card.get("alpha"),
                "beta": card.get("beta"),
                "sortino": card.get("sortinoRatio"),
                "pe": card.get("pe"),
                "pb": card.get("pb"),
            }
        )
    return {"funds": funds}


# ── featured theme listing (SSR cards) ──────────────────────────────────────


def parse_featured(html: str) -> dict:
    """Featured/theme pages render .mfFund-block cards server-side."""
    soup = BeautifulSoup(html, "lxml")
    blocks = soup.select(".mfFund-block")
    funds = []
    seen: set[int] = set()
    for b in blocks:
        a = b.select_one(".scheme-name a[href]")
        if not a:
            continue
        href = str(a.get("href", ""))
        m = re.search(r"/mutual-funds/([a-z0-9-]+)/(\d+)", href)
        if not m:
            continue
        sid = int(m.group(2))
        if sid in seen:
            continue
        seen.add(sid)
        returns = {}
        for span in b.select(".return-list .percent"):
            classes = span.get("class") or []
            period = next((c for c in classes if c.startswith("period-")), "")
            if period:
                returns[period.removeprefix("period-")] = _clean(span.get_text())
        funds.append(
            {
                "scheme_id": sid,
                "slug": m.group(1),
                "name": _clean(a.get_text()),
                "url": href,
                "returns_pct": returns,
            }
        )
    title_el = soup.select_one("h1")
    return {
        "title": _clean(title_el.get_text()) if title_el else "",
        "count": len(funds),
        "funds": funds,
    }


# ── AMC (fund house) page ───────────────────────────────────────────────────


def parse_amc_schemes(html: str) -> dict:
    """Fund-house pages embed mfAmcSchemeDTO with all schemes of that AMC."""
    schemes = parse_js_var(html, "mfAmcSchemeDTO")
    if not isinstance(schemes, list):
        raise UpstreamError("AMC scheme list missing from page")
    out = []
    for s in schemes:
        if not isinstance(s, dict):
            continue
        rets = s.get("schemeReturn") or s.get("mfReturnDetails") or {}
        out.append(
            {
                "scheme_id": s.get("schemeId"),
                "name": s.get("nameOfScheme") or s.get("schemeName"),
                "category": s.get("categoryName") or s.get("secondaryCategory"),
                "riskometer": s.get("riskometer"),
                "nav": s.get("navValue") or s.get("nav"),
                "returns_pct": {k: v for k, v in rets.items() if isinstance(v, (int, float))},
            }
        )
    return {"count": len(out), "schemes": out}


# ── listing/search API normalizers (JSON already, just shape it) ────────────


def normalize_listing(payload: dict) -> dict:
    """Shape get-all-regular-funds-listing payloads into agent-friendly dicts."""
    items = []
    amc_map = payload.get("amcMap") or {}
    for f in payload.get("mfSchemeMiniList") or []:
        rtn = f.get("rtnDet") or {}
        items.append(
            {
                "scheme_id": f.get("sId"),
                "name": f.get("parName") or f.get("name"),
                "full_name": f.get("name"),
                "amc": f.get("amcName"),
                "amc_id": f.get("aId"),
                "group": f.get("pCat"),
                "category": f.get("catDispName") or f.get("etmCtDisplayName"),
                "category_id": f.get("etmCat"),
                "url": f.get("sdWebUrl"),
                "nav": f.get("lNv"),
                "nav_date": (f.get("lNvD") or {}).get("value"),
                "expense_ratio_pct": f.get("expRat"),
                "aum_cr": f.get("asSz"),
                "aum_display": f.get("assetSizeFor"),
                "etm_rank": f.get("etmRnk"),
                "risk_label": ((f.get("rskratpoint") or [None])[0]),
                "lock_in_days": f.get("lockinDays"),
                "is_direct": f.get("isD"),
                "buyable": f.get("isBuyable"),
                "returns_pct": {k: v for k, v in rtn.items() if isinstance(v, (int, float))},
            }
        )
    cats = []
    for c in payload.get("etmCategoryList") or []:
        cats.append(
            {
                "id": c.get("id"),
                "group": c.get("primary"),
                "display": c.get("secondary") or c.get("name"),
            }
        )
    return {
        "total": payload.get("totalSize"),
        "returned": len(items),
        "page": payload.get("page_id"),
        "funds": items,
        "categories": cats,
        "amcs": {str(k): v for k, v in amc_map.items()} if isinstance(amc_map, dict) else {},
    }


def normalize_search(payload: dict) -> dict:
    results = []
    for f in payload.get("mfBasicDetailList") or []:
        results.append(
            {
                "scheme_id": f.get("schemeId"),
                "name": f.get("nameOfScheme"),
                "parent_name": f.get("parentName"),
                "amc_id": f.get("amcId"),
                "buyable": f.get("isBuyable"),
                "is_nfo": f.get("isNfo"),
                "3y_return_pct": f.get("threeYearReturn"),
                "url": f.get("sdWebUrl"),
            }
        )
    return {"total": payload.get("totalCount") or len(results), "results": results}


def dumps(obj) -> str:
    """Compact JSON dump helper used by CLI when --json requested."""

    def _default(o):
        return str(o)

    return json.dumps(obj, default=_default, separators=(",", ":"))


__all__ = [
    "parse_amc_schemes",
    "parse_compare",
    "parse_featured",
    "parse_fund_detail",
    "find_key",
    "normalize_listing",
    "normalize_search",
]
