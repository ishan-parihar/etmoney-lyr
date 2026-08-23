"""Stock parsers: extract structured data from Next.js RSC flight payloads."""

import json
import re

from etmoney_lyr.exceptions import UpstreamError
from etmoney_lyr.jsvars import extract_rsc_payload, find_json_objects, find_value


def _f(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", ""))
        except ValueError:
            return None
    return None


def parse_stock_list(html: str) -> dict:
    """Screens / indices / sectors pages all carry a ``stockList`` array in RSC data."""
    payload = extract_rsc_payload(html)
    if not payload:
        raise UpstreamError("no RSC payload on page (layout changed or non-stock page)")
    vals = find_value(payload, "stockList", limit=1)
    stocks_raw = vals[0] if vals else None
    if not isinstance(stocks_raw, list):
        raise UpstreamError("stockList missing from RSC payload")
    stocks = []
    for s in stocks_raw:
        if not isinstance(s, dict):
            continue
        ltp_time = (s.get("lastTradedPriceDateTime") or {}).get("value")
        stocks.append(
            {
                "stock_id": s.get("stockId"),
                "name": s.get("displayName"),
                "scrip": s.get("scripCode"),
                "market_cap_bucket": s.get("mktCapDesc"),
                "market_cap_inr": _f(s.get("mktCap")),
                "price": _f(s.get("currPrice")),
                "prev_close": _f(s.get("prevClose")),
                "return_1d_pct": _f(s.get("returnPerc1D") or s.get("oneDayReturnPerc")),
                "pe": _f(s.get("ratioPE")),
                "industry": s.get("industryName"),
                "high_52w": _f(s.get("high52W")),
                "low_52w": _f(s.get("low52W")),
                "volume": s.get("currVol"),
                "url": s.get("stockUrl"),
                "ltp_time": ltp_time,
            }
        )
    title_m = re.search(r'"pageName":"([^"]+)"', payload)
    return {
        "title": title_m.group(1) if title_m else "",
        "count": len(stocks),
        "stocks": stocks,
    }


def parse_stock_detail(html: str) -> dict:
    """Stock overview page: company block + returns + fundamentals table."""
    payload = extract_rsc_payload(html)
    if not payload:
        raise UpstreamError("no RSC payload on page")

    company = None
    # The company block has companyCode + price + delta at top level.
    for obj in find_json_objects(payload, "companyCode", limit=3):
        if "price" in obj and "displayName" in obj:
            company = obj
            break
    if not company:
        raise UpstreamError("company block missing from RSC payload")

    def ret(key: str) -> float | None:
        return _f(company.get(key))

    about = ""
    m = re.search(r"\n[0-9a-f]+:T[0-9a-f]+,(The company was established[^\n]*)", payload)
    if m:
        about = m.group(1).replace("{TODAY}", "").replace("{MKT_CAP}", "").strip()

    fundamentals = []
    for table in find_value(payload, "tableData", limit=1):
        if not isinstance(table, list):
            continue
        for row in table:
            if not isinstance(row, dict):
                continue
            name = row.get("stockName")
            if not name:
                continue
            fundamentals.append(
                {
                    "name": name,
                    "stock_id": row.get("stockId"),
                    "ltp": _f(row.get("ltp")),
                    "net_change": row.get("netChange"),
                    "market_cap_cr": row.get("marketCap"),
                    "pb": row.get("priceToBv"),
                    "roe_pct": row.get("roe"),
                    "roa_pct": row.get("roa"),
                    "nim_pct": row.get("nim"),
                    "eps_growth": row.get("epsGrowth"),
                }
            )
        if fundamentals:
            break

    return {
        "stock_id": company.get("stockId"),
        "name": company.get("displayName"),
        "short_name": company.get("shortCompanyName"),
        "scrip": company.get("scripCode"),
        "exchange_id": company.get("exchangeId"),
        "price": _f(company.get("price")),
        "delta": _f(company.get("delta")),
        "delta_pct": _f(company.get("deltaPercent")),
        "returns_pct": {
            "1w": ret("oneWeekReturn"),
            "1m": ret("oneMonthReturn"),
            "3m": ret("threeMonthReturn"),
            "6m": ret("sixMonthReturn"),
            "1y": ret("oneYearReturn"),
            "3y": ret("threeYearReturn"),
            "5y": ret("fiveYearReturn"),
            "10y": ret("tenYearReturn"),
            "15y": ret("fifteenYearReturn"),
        },
        "upside_potential_score": company.get("upsidePotential"),
        "financial_strength_score": company.get("financialStrength"),
        "about": about[:800] if about else "",
        "fundamentals_peers": fundamentals,
    }


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str)
