"""Mutual fund research tools — all 67 categories across equity/debt/hybrid/commodities.

Logic lives in module-level async functions (directly callable by tests/CLI);
register_fund_tools wraps them for MCP.
"""

from typing import Literal

from fastmcp import FastMCP

from etmoney_lyr.constants import (
    DURATIONS,
    FEATURED_URL,
    FUND_URL,
    INVESTMENT_MODES,
    SORT_TYPES,
    THEMES,
)
from etmoney_lyr.exceptions import ValidationError
from etmoney_lyr.parsers.funds import (
    normalize_listing,
    normalize_search,
    parse_compare,
    parse_featured,
    parse_fund_detail,
)
from etmoney_lyr.tools.common import get_client, handle_api_error

DurationKey = Literal["1m", "3m", "6m", "1y", "3y", "5y", "10y"]
ModeKey = Literal["sip", "lumpsum"]
SortKey = Literal["etm_rank", "returns", "fund_size"]

_MAX_PAGE_SIZE = 50


async def _categories_from_upstream() -> list[dict]:
    data = await get_client().fund_listing_raw(
        categoryId="",
        returnConsistensy=0,
        vroRating=0,
        fundSize=0,
        fundHouse="",
        duration=DURATIONS["1y"],
        investmentMode=INVESTMENT_MODES["lumpsum"],
        sortType=SORT_TYPES["returns"],
        sortOrder="desc",
        size=1,
        page=0,
    )
    return [
        {
            "id": c.get("id"),
            "group": c.get("primary"),
            "display": c.get("secondary") or c.get("name"),
        }
        for c in data.get("etmCategoryList") or []
    ]


def _resolve_category(category: str | None, categories: list[dict]) -> int | None:
    """Accept a numeric id or case-insensitive display-name / substring match."""
    if category is None or str(category).strip() == "":
        return None
    s = str(category).strip()
    if s.isdigit():
        return int(s)
    low = s.lower()
    for c in categories:
        disp = (c.get("display") or "").lower()
        name = (c.get("name") or "").lower()
        if low in (disp, name):
            return int(c["id"])
    matches = [c for c in categories if low in (c.get("display") or "").lower()]
    if len(matches) == 1:
        return int(matches[0]["id"])
    raise ValidationError(
        f"unknown category '{category}'",
        hint="call mf_categories to list valid ids and names",
    )


def _listing_params(
    cat_id_param: str, duration, investment_mode, sort_by, sort_order, size, page
) -> dict:
    return {
        "categoryId": cat_id_param,
        "returnConsistensy": 0,
        "vroRating": 0,
        "fundSize": 0,
        "fundHouse": "",
        "duration": DURATIONS[duration],
        "investmentMode": INVESTMENT_MODES[investment_mode],
        "sortType": SORT_TYPES[sort_by],
        "sortOrder": sort_order,
        "size": size,
        "page": page,
    }


# ── tool implementations ────────────────────────────────────────────────────


async def mf_search(query: str, limit: int = 10) -> dict:
    """Search mutual funds by name (e.g. 'parag parikh flexi', 'small cap')."""
    try:
        q = query.strip()
        if len(q) < 2:
            raise ValidationError("query must be >= 2 chars")
        data = await get_client().search_funds_raw(q[:60])
        norm = normalize_search(data)
        norm["results"] = norm["results"][: max(1, min(limit, 30))]
        norm["ok"] = True
        return norm
    except Exception as e:
        return handle_api_error(e)


async def mf_list(
    category: str | None = None,
    group: Literal["EQUITY", "DEBT", "HYBRID", "COMMODITIES", "OTHERS"] | None = None,
    duration: DurationKey = "1y",
    investment_mode: ModeKey = "lumpsum",
    sort_by: SortKey = "returns",
    sort_order: Literal["asc", "desc"] = "desc",
    page: int = 0,
    size: int = 20,
) -> dict:
    """Browse/screen funds across all 67 categories (index, gold, silver, FoF,
    sectoral, debt durations, hybrid, retirement, international...)."""
    try:
        cats = await _categories_from_upstream()
        cat_id = _resolve_category(category, cats)
        if group and cat_id is None:
            cat_id_param = ",".join(str(c["id"]) for c in cats if c.get("group") == group)
        else:
            cat_id_param = str(cat_id) if cat_id is not None else ""

        if not 1 <= size <= _MAX_PAGE_SIZE:
            raise ValidationError(f"size must be 1..{_MAX_PAGE_SIZE}", hint=f"got {size}")
        if page < 0:
            raise ValidationError("page must be >= 0")

        data = await get_client().fund_listing_raw(
            **_listing_params(
                cat_id_param, duration, investment_mode, sort_by, sort_order, size, page
            )
        )
        norm = normalize_listing(data)
        norm.pop("categories", None)
        norm.pop("amcs", None)
        norm["category_filter_applied"] = {"input": category, "group": group, "resolved_id": cat_id}
        norm["query"] = {
            "duration": duration,
            "investment_mode": investment_mode,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "page": page,
            "size": size,
        }
        norm["ok"] = True
        return norm
    except Exception as e:
        return handle_api_error(e)


async def mf_detail(scheme_id: int) -> dict:
    """Full fund report card by scheme id: NAV, returns vs category, expense
    breakdown, holdings, sectors, risk ratios, peers, managers, tax treatment."""
    try:
        html = await get_client().get_html(FUND_URL.format(slug="fund", scheme_id=scheme_id))
        result = parse_fund_detail(html)
        result["ok"] = True
        return result
    except Exception as e:
        return handle_api_error(e)


async def mf_compare(scheme_ids: list[int]) -> dict:
    """Side-by-side compare of 2-4 funds (returns, risk ratios, expense, rank)."""
    try:
        try:
            ids = [int(i) for i in scheme_ids]
        except (TypeError, ValueError) as e:
            raise ValidationError(f"invalid scheme id: {e}") from e
        if len(set(ids)) != len(ids):
            raise ValidationError("duplicate scheme ids in compare list")
        if len(ids) < 2:
            raise ValidationError("need at least 2 scheme ids", hint="e.g. [19230, 25643]")
        if len(ids) > 4:
            raise ValidationError("at most 4 funds can be compared")
        html = await get_client().get_html(
            "/mutual-funds/compare", params={"schemeIds": ",".join(str(i) for i in ids)}
        )
        result = parse_compare(html)
        result["ok"] = True
        return result
    except Exception as e:
        return handle_api_error(e)


async def mf_categories() -> dict:
    """All fund categories with ids (use with mf_list's `category` param)."""
    try:
        cats = await _categories_from_upstream()
        groups: dict[str, int] = {}
        for c in cats:
            groups[c["group"]] = groups.get(c["group"], 0) + 1
        return {"ok": True, "total_categories": len(cats), "groups": groups, "categories": cats}
    except Exception as e:
        return handle_api_error(e)


async def mf_featured(theme: str) -> dict:
    """ET Money curated lists: best_mutual_funds, best_sip_funds, best_index_funds,
    best_gold_funds, low_risk, high_return, retirement, beginners, better_than_fd..."""
    try:
        key = theme.strip().lower().replace("-", "_").replace(" ", "_")
        path = THEMES.get(key)
        if not path:
            raise ValidationError(
                f"unknown theme '{theme}'", hint=f"valid themes: {', '.join(sorted(THEMES))}"
            )
        slug, _, page_id = path.partition("/")
        html = await get_client().get_html(FEATURED_URL.format(slug=slug, id=page_id))
        result = parse_featured(html)
        result["theme"] = key
        result["ok"] = True
        return result
    except Exception as e:
        return handle_api_error(e)


def register_fund_tools(mcp: FastMCP) -> int:
    for fn in (mf_search, mf_list, mf_detail, mf_compare, mf_categories, mf_featured):
        mcp.tool()(fn)
    return 6
