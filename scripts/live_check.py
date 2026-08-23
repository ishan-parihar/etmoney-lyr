"""Live end-to-end verification of etmoney-lyr against the real etmoney.com.

Run manually (network required):
    uv run python scripts/live_check.py

Exercises every tool across its full parameter space plus cross-source data
consistency checks. Exits non-zero on any failure.
"""

import asyncio
import sys

sys.path.insert(0, ".")

PASS = []
FAIL = []


def check(name: str, cond: bool, detail: str = ""):
    (PASS if cond else FAIL).append((name, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")


async def main():
    from etmoney_lyr.constants import SCREENS, SECTORS
    from etmoney_lyr.tools.funds import (
        mf_categories,
        mf_compare,
        mf_detail,
        mf_featured,
        mf_list,
        mf_search,
    )
    from etmoney_lyr.tools.stocks import (
        index_stocks,
        sector_stocks,
        stock_detail,
        stock_screen,
    )

    # ── funds: search ──────────────────────────────────────────────────────
    r = await mf_search("parag parikh")
    check(
        "search: known term",
        r["ok"] and any(x["scheme_id"] == 19230 for x in r["results"]),
        f"total={r['total']}",
    )
    r = await mf_search("zzqqxx nonexistent fund")
    check("search: no results", r["ok"] and r["total"] == 0, "")
    r = await mf_search("a")
    check("search: short query structured", not r["ok"] and r["error"] == "validation", "")

    # ── funds: categories & listing across ALL groups ─────────────────────
    cats = await mf_categories()
    check(
        "categories: >=60 across 4+ groups",
        cats["ok"] and cats["total_categories"] >= 60 and len(cats["groups"]) >= 4,
        str(cats.get("groups")),
    )
    cat_list = cats["categories"]

    for group in ["EQUITY", "DEBT", "HYBRID", "COMMODITIES"]:
        r = await mf_list(group=group, size=5)
        ok = r["ok"] and r["total"] > 0 and len(r["funds"]) == 5
        f0 = r["funds"][0] if r["funds"] else {}
        check(f"list[{group}]", ok, f"total={r['total']} first={f0.get('category')}")
        if ok:
            assert all(isinstance(f["scheme_id"], int) for f in r["funds"])

    # named category resolution per group
    by_display = {}
    for c in cat_list:
        by_display.setdefault(c["display"].lower(), c)
    for probe in ["flexi cap", "liquid", "balanced advantage", "gold", "small cap index"]:
        if probe in by_display:
            r = await mf_list(category=probe, size=2)
            resolved = r.get("category_filter_applied", {}).get("resolved_id")
            check(
                f"list[category={probe}]",
                r["ok"] and resolved == by_display[probe]["id"],
                f"id={resolved}",
            )

    # sort / mode / order matrix
    for kwargs in [
        {"sort_by": "returns", "sort_order": "asc"},
        {"sort_by": "fund_size", "sort_order": "desc"},
        {"investment_mode": "sip", "duration": "5y"},
    ]:
        r = await mf_list(size=3, **kwargs)
        check(f"list[{kwargs}]", r["ok"] and r["total"] > 0, "")

    # pagination boundary: last page must return <= size rows, page beyond end returns []
    r0 = await mf_list(category="gold", size=20, page=0)
    total = r0["total"]
    last_page = (total - 1) // 20 if total else 0
    rl = await mf_list(category="gold", size=20, page=last_page)
    ro = await mf_list(category="gold", size=20, page=last_page + 3)
    check(
        "pagination boundary",
        rl["ok"] and 0 < len(rl["funds"]) <= 20 and ro["ok"] and ro["funds"] == [],
        f"total={total} last_page_rows={len(rl['funds'])}",
    )
    r = await mf_list(size=99)
    check("list: size>50 structured error", not r["ok"] and r["error"] == "validation", "")

    # ── featured themes ────────────────────────────────────────────────────
    for theme in ["best_sip_funds", "best_gold_funds", "best_index_funds", "low_risk"]:
        r = await mf_featured(theme)
        check(f"featured[{theme}]", r["ok"] and r["count"] > 0, f"n={r['count']}")
    r = await mf_featured("bogus_theme")
    check(
        "featured: unknown theme hint", not r["ok"] and "valid themes" in (r.get("hint") or ""), ""
    )

    # ── fund detail across fund TYPES ─────────────────────────────────────
    probes = {
        "equity-flexicap": 19230,  # Parag Parikh Flexi Cap
        "debt-liquid": None,  # resolve below
        "gold": None,  # resolve below
        "index-nifty50": None,  # resolve below
    }
    for label, cat in [
        ("debt-liquid", "liquid"),
        ("gold", "gold"),
        ("index-nifty50", "large cap index"),
    ]:
        rr = await mf_list(category=cat, size=1)
        probes[label] = rr["funds"][0]["scheme_id"] if rr["funds"] else None

    details = {}
    for label, sid in probes.items():
        if sid is None:
            check(f"detail[{label}] resolve", False, "no fund found in category")
            continue
        d = await mf_detail(sid)
        ok = (
            d["ok"]
            and d["name"]
            and isinstance(d["holdings"], list)
            and isinstance(d["trailing_returns"], list)
            and len(d["peers"]) >= 1
        )
        check(
            f"detail[{label}] sid={sid}",
            ok,
            f"holdings={len(d.get('holdings', []))} peers={len(d.get('peers', []))}",
        )
        if ok:
            details[label] = d

    r = await mf_detail(99999999)
    check("detail: invalid id -> not_found", not r["ok"] and r["error"] == "not_found", "")

    # debt funds may legitimately have no equity holdings — schema must hold
    dl = details.get("debt-liquid")
    if dl:
        check(
            "detail[debt]: no crash on empty equities",
            dl["ok"] and isinstance(dl["asset_allocation"], dict),
            "",
        )

    # ── compare ────────────────────────────────────────────────────────────
    ids = list(
        dict.fromkeys(
            [
                p
                for p in [probes.get("equity-flexicap")]
                + [d["scheme_id"] for d in details.values()]
                if p
            ]
        )
    )[:3]
    if len(ids) >= 2:
        r = await mf_compare(ids[:3])
        check(f"compare x{len(ids)}", r["ok"] and len(r["funds"]) == min(3, len(ids)), "")
    r = await mf_compare([19230])
    check("compare: 1 id structured", not r["ok"] and r["error"] == "validation", "")
    r = await mf_compare([1, 2, 3, 4, 5])
    check("compare: 5 ids structured", not r["ok"] and r["error"] == "validation", "")

    # ── stocks: ALL screens ────────────────────────────────────────────────
    for screen in SCREENS:
        r = await stock_screen(screen, limit=5)
        ok = r["ok"] and len(r["stocks"]) == 5 and r["stocks"][0]["name"]
        check(f"screen[{screen}]", ok, f"first={r['stocks'][0]['name'] if r['stocks'] else '-'}")

    # ── stocks: indices (incl. 500-row stress) ─────────────────────────────
    for idx in ["nifty_50", "nifty_500", "nifty_bank", "nifty_smallcap_250"]:
        cap = 600 if idx == "nifty_500" else 10
        r = await index_stocks(idx, limit=cap)
        want_min = 400 if idx == "nifty_500" else 5
        check(f"index[{idx}]", r["ok"] and len(r["stocks"]) >= want_min, f"rows={len(r['stocks'])}")

    # ── stocks: sectors ────────────────────────────────────────────────────
    for sector in list(SECTORS)[:4]:
        r = await sector_stocks(sector, limit=5)
        check(f"sector[{sector}]", r["ok"] and len(r["stocks"]) == 5, "")

    # ── stock detail: both ref forms ───────────────────────────────────────
    g = await stock_screen("top_gainers", limit=1)
    sid = g["stocks"][0]["stock_id"]
    url = g["stocks"][0]["url"]
    r1 = await stock_detail(str(sid))
    r2 = await stock_detail(url)
    check(
        "stock_detail: bare id + slug path agree",
        r1["ok"] and r2["ok"] and r1["name"] == r2["name"],
        r1.get("name", ""),
    )
    r = await stock_detail("../bad input")
    check("stock_detail: invalid ref structured", not r["ok"] and r["error"] == "validation", "")

    # ── cross-source consistency ───────────────────────────────────────────
    pp = details.get("equity-flexicap")
    if pp:
        lst = await mf_list(category="flexi cap", size=50)
        match = next((f for f in lst["funds"] if f["scheme_id"] == 19230), None)
        if match:
            check(
                "consistency: listing nav present vs detail",
                match["nav"] is not None and pp["expense_ratio_total_pct"] is not None,
                f"listing_nav={match['nav']} detail_expense={pp['expense_ratio_total_pct']}",
            )
        cmp_ = await mf_compare([19230, 25643])
        tile = cmp_["funds"][0]
        trailing_1y = next(
            (t["fund_pct"] for t in pp["trailing_returns"] if t["period"] == "1 Year"), None
        )
        check(
            "consistency: compare 1Y return == detail trailing 1Y",
            tile["returns_pct"].get("365") is not None
            and abs(tile["returns_pct"]["365"] - trailing_1y) < 0.15,
            f"compare={tile['returns_pct'].get('365')} detail={trailing_1y}",
        )
        holdings_top = {h["name"]: h["pct"] for h in pp["holdings"]}
        check(
            "consistency: top holding pct sums sane",
            sum(ppct for ppct in list(holdings_top.values())[:10]) < 100,
            "",
        )

    # ── summary ────────────────────────────────────────────────────────────
    print("\n==============================")
    print(f"PASSED: {len(PASS)}   FAILED: {len(FAIL)}")
    if FAIL:
        for name, detail in FAIL:
            print(f"  FAIL: {name} {detail}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
