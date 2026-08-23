"""Stock research tools: market screens, index/sector constituents, stock detail."""

import re
from typing import Literal

from fastmcp import FastMCP

from etmoney_lyr.constants import (
    INDEX_URL,
    INDICES,
    SCREENS,
    SECTOR_URL,
    SECTORS,
    STOCK_DETAIL_URL,
    STOCK_SCREEN_URL,
)
from etmoney_lyr.exceptions import ValidationError
from etmoney_lyr.parsers.stocks import parse_stock_detail, parse_stock_list
from etmoney_lyr.tools.common import get_client, handle_api_error

ScreenKey = Literal[
    "top_gainers",
    "top_losers",
    "52w_high",
    "52w_low",
    "all_time_high",
    "all_time_low",
    "high_dividend_yield",
    "bluechip",
    "multibagger",
    "most_active",
]
IndexKey = Literal[
    "nifty_50",
    "nifty_next_50",
    "nifty_100",
    "nifty_200",
    "nifty_500",
    "nifty_midcap_50",
    "nifty_midcap_150",
    "nifty_smallcap_250",
    "nifty_bank",
    "nifty_fmcg",
]
SectorKey = Literal[
    "automobiles",
    "banking",
    "defence",
    "fmcg",
    "healthcare",
    "it_software",
    "refineries",
    "pharmaceuticals",
    "power",
    "telecom",
]

_STOCK_REF_RE = re.compile(r"/?(?:stocks/)?([a-z0-9.-]+)/(\d+)")


def _listing_url(template: str, slug_id: str) -> str:
    slug, _, page_id = slug_id.partition("/")
    return template.format(slug=slug, id=page_id)


def _clip(stocks: list, limit: int, cap: int) -> list:
    return stocks[: max(1, min(limit, cap))]


async def stock_screen(screen: ScreenKey, limit: int = 25) -> dict:
    """ET Money market-data screens (gainers/losers/52w extremes/multibagger/
    bluechip/most active/dividend yield) with price, PE, market cap per stock."""
    try:
        if screen not in SCREENS:
            raise ValidationError(f"unknown screen '{screen}'")
        html = await get_client().get_html(_listing_url(STOCK_SCREEN_URL, SCREENS[screen]))
        result = parse_stock_list(html)
        result["stocks"] = _clip(result["stocks"], limit, 250)
        result["screen"] = screen
        result["ok"] = True
        return result
    except Exception as e:
        return handle_api_error(e)


async def index_stocks(index: IndexKey, limit: int = 50) -> dict:
    """Constituents of major NSE indices with live metrics."""
    try:
        if index not in INDICES:
            raise ValidationError(f"unknown index '{index}'")
        html = await get_client().get_html(_listing_url(INDEX_URL, INDICES[index]))
        result = parse_stock_list(html)
        result["stocks"] = _clip(result["stocks"], limit, 600)
        result["index"] = index
        result["ok"] = True
        return result
    except Exception as e:
        return handle_api_error(e)


async def sector_stocks(sector: SectorKey, limit: int = 50) -> dict:
    """Stocks grouped by ET Money sector pages."""
    try:
        if sector not in SECTORS:
            raise ValidationError(f"unknown sector '{sector}'")
        html = await get_client().get_html(_listing_url(SECTOR_URL, SECTORS[sector]))
        result = parse_stock_list(html)
        result["stocks"] = _clip(result["stocks"], limit, 500)
        result["sector"] = sector
        result["ok"] = True
        return result
    except Exception as e:
        return handle_api_error(e)


async def stock_detail(stock_ref: str) -> dict:
    """Stock overview by numeric id or '/stocks/<slug>/<id>' path: price, day
    change, returns across horizons, scores, peer fundamentals."""
    try:
        ref = stock_ref.strip().strip("/")
        if ref.isdigit():
            path = STOCK_DETAIL_URL.format(slug="stock", stock_id=ref)
        else:
            m = _STOCK_REF_RE.fullmatch(ref)
            if not m:
                raise ValidationError(
                    f"invalid stock_ref '{stock_ref}'",
                    hint="pass a numeric id or '/stocks/<slug>/<id>'",
                )
            path = f"/stocks/{m.group(1)}/{m.group(2)}"
        html = await get_client().get_html(path)
        result = parse_stock_detail(html)
        result["ok"] = True
        return result
    except Exception as e:
        return handle_api_error(e)


def register_stock_tools(mcp: FastMCP) -> int:
    for fn in (stock_screen, index_stocks, sector_stocks, stock_detail):
        mcp.tool()(fn)
    return 4
