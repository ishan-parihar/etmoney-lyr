"""etmoney-lyr CLI — AXI-compliant agent-facing interface.

Output discipline: data on stdout in TOON (default) or JSON (--json);
structured errors on stdout with exit code 2; logs on stderr only.
"""

import argparse
import asyncio
import json
import sys

from etmoney_lyr import __version__
from etmoney_lyr.constants import SCREENS, THEMES

# ── TOON helpers (family convention, adapted from reddit-lyr) ───────────────


def _toon_quote(val: str) -> str:
    if val == "":
        return '""'
    needs_quote = (
        val in ("true", "false", "null")
        or val.lstrip("-").replace(".", "", 1).isdigit()
        or any(c in val for c in (":", ",", '"', "[", "]", "{", "}", "#"))
        or val.startswith(("-", "#", " "))
        or val.endswith(" ")
        or val.startswith('"')
        or val.endswith('"')
    )
    if needs_quote:
        return '"' + val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return val


def _toon_kv(key: str, val) -> str:
    if val is None:
        return f"{key}: null"
    if isinstance(val, bool):
        return f"{key}: {'true' if val else 'false'}"
    if isinstance(val, (int, float)):
        return f"{key}: {val}"
    return f"{key}: {_toon_quote(str(val))}"


def axi_error(msg: str, hint: str | None = None) -> None:
    print(_toon_kv("error", msg))
    if hint:
        print(_toon_kv("help", hint))
    sys.exit(2)


def _emit(obj, as_json: bool, indent: int = 0):
    """Render a dict/list in TOON (flat/one-level) or JSON."""
    pad = "  " * indent
    if as_json:
        print(json.dumps(obj, default=str, indent=None, separators=(",", ":")))
        return
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                flat = {k: v for k, v in item.items() if not isinstance(v, (dict, list))}
                print(pad + " ".join(_toon_kv(k, v) for k, v in flat.items()))
            else:
                print(pad + _toon_quote(str(item)))
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                print(f"{pad}{k}:")
                _emit(v, False, indent + 1)
            elif isinstance(v, list):
                if not v:
                    print(f"{pad}{k}: []")
                    continue
                scalar_list = all(not isinstance(i, (dict, list)) for i in v)
                if scalar_list and len(v) <= 12:
                    print(pad + _toon_kv(k, ", ".join(str(i) for i in v)))
                else:
                    print(f"{pad}{k}: [{len(v)} items]")
                    _emit(v[:20], False, indent + 1)
                    if len(v) > 20:
                        print(f"{pad}  ... ({len(v) - 20} more)")
            else:
                print(pad + _toon_kv(k, v))


def _out(obj, as_json: bool) -> None:
    """Standard success envelope: strip ok flag in TOON, keep in JSON."""
    if isinstance(obj, dict) and not as_json:
        obj = {k: v for k, v in obj.items() if k != "ok"}
    _emit(obj, as_json)


# ── async runners per command ───────────────────────────────────────────────


async def run_search(args, as_json: bool) -> None:
    from etmoney_lyr.parsers.funds import normalize_search
    from etmoney_lyr.tools.common import get_client

    data = await get_client().search_funds_raw(args.query)
    norm = normalize_search(data)
    norm["results"] = norm["results"][: args.limit]
    if not norm["results"]:
        print(_toon_kv("results", "none"))
        print(_toon_kv("help", "try a broader name, e.g. 'flexi' instead of full fund name"))
        return
    _out(norm, as_json)


async def run_funds(args, as_json: bool) -> None:
    from etmoney_lyr.tools.funds import mf_list  # reuse tool logic incl. category resolution

    result = await mf_list(
        category=args.category,
        group=args.group,
        duration=args.duration,
        investment_mode=args.mode,
        sort_by=args.sort_by,
        sort_order=args.order,
        page=args.page,
        size=args.size,
    )
    if not result.get("ok", True):
        axi_error(result.get("message", "request failed"), result.get("hint"))
        return
    funds = result.pop("funds", [])
    meta = {k: v for k, v in result.items() if k != "amcs"}
    meta["showing"] = len(funds)
    _out(meta, as_json)
    if funds:
        print()
        _out(funds, as_json)


async def run_fund(args, as_json: bool) -> None:
    from etmoney_lyr.parsers.funds import parse_fund_detail
    from etmoney_lyr.tools.common import get_client

    html = await get_client().get_html(f"/mutual-funds/fund/{args.scheme_id}")
    d = parse_fund_detail(html)
    core = {
        "scheme_id": d["scheme_id"],
        "name": d["name"],
        "riskometer": d["riskometer"],
        "aum": d["aum"],
        "expense_ratio_total_pct": d["expense_ratio_total_pct"],
        "benchmark": d["benchmark"],
        "holdings_count": len(d["holdings"]),
        "peers_count": len(d["peers"]),
    }
    _out(core if not args.full else d, as_json)
    if not args.full:
        print(_toon_kv("help", "--full includes holdings, trailing returns, peers, managers"))


async def run_compare(args, as_json: bool) -> None:
    from etmoney_lyr.parsers.funds import parse_compare
    from etmoney_lyr.tools.common import get_client

    ids = [i.strip() for i in args.scheme_ids.split(",") if i.strip()]
    if len(ids) < 2 or len(ids) > 4:
        axi_error("compare needs 2..4 comma-separated scheme ids", "e.g. compare 19230,25643")
        return
    html = await get_client().get_html("/mutual-funds/compare", params={"schemeIds": ",".join(ids)})
    _out(parse_compare(html), as_json)


async def run_categories(as_json: bool) -> None:
    from etmoney_lyr.tools.funds import mf_categories

    _out(await mf_categories(), as_json)


async def run_featured(args, as_json: bool) -> None:
    from etmoney_lyr.tools.funds import mf_featured

    result = await mf_featured(theme=args.theme)
    if not result.get("ok", True):
        axi_error(result.get("message", "failed"), result.get("hint"))
        return
    funds = result.pop("funds", [])
    _out(result, as_json)
    if funds:
        print()
        _out(funds, as_json)


async def run_stocks(args, as_json: bool) -> None:
    from etmoney_lyr.tools.stocks import stock_screen

    result = await stock_screen(screen=args.screen, limit=args.limit)
    if not result.get("ok", True):
        axi_error(result.get("message", "failed"), result.get("hint"))
        return
    stocks = result.pop("stocks", [])
    meta = {"screen": result.get("screen"), "count": len(stocks)}
    _out(meta, as_json)
    if stocks:
        print()
        _out(stocks, as_json)


async def run_listing_page(kind: str, key: str, limit: int, as_json: bool) -> None:
    from etmoney_lyr.tools.stocks import index_stocks, sector_stocks

    fn = index_stocks if kind == "index" else sector_stocks
    result = (
        await fn(index=key, limit=limit) if kind == "index" else await fn(sector=key, limit=limit)
    )
    if not result.get("ok", True):
        axi_error(result.get("message", "failed"), result.get("hint"))
        return
    stocks = result.pop("stocks", [])
    meta = {k: v for k, v in result.items() if k != "title"}
    meta["count"] = len(stocks)
    _out(meta, as_json)
    if stocks:
        print()
        _out(stocks, as_json)


async def run_stock_detail(args, as_json: bool) -> None:
    from etmoney_lyr.parsers.stocks import parse_stock_detail
    from etmoney_lyr.tools.common import get_client

    ref = args.stock_ref.strip().strip("/")
    path = f"/stocks/{ref}" if "/" in ref else f"/stocks/stock/{ref}"
    html = await get_client().get_html(path)
    d = parse_stock_detail(html)
    core = {
        "name": d["name"],
        "price": d["price"],
        "delta_pct": d["delta_pct"],
        "return_1y_pct": d["returns_pct"]["1y"],
        "peers_count": len(d["fundamentals_peers"]),
    }
    _out(core if not args.full else d, as_json)


async def run_status() -> None:
    from etmoney_lyr.client import EtMoneyClient

    client = EtMoneyClient(timeout=8.0)
    try:
        resp = await client.request("/")
        print(_toon_kv("status", "upstream_reachable"))
        print(_toon_kv("http", resp.status_code))
    except Exception as e:
        print(_toon_kv("status", "unreachable"))
        print(_toon_kv("detail", str(e)))
    finally:
        await client.aclose()


# ── parser assembly ─────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="etmoney-lyr",
        description="ET Money research layer — mutual funds & stocks for AI agents",
    )
    p.add_argument("--version", action="version", version=f"etmoney-lyr {__version__}")
    p.add_argument("--json", action="store_true", help="output raw JSON instead of TOON")
    p.add_argument("--list-tools", action="store_true", help="list MCP tools")
    p.add_argument("--fields", help="with --list-tools: filter fields containing this substring")

    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("search", help="search mutual funds by name")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)

    s = sub.add_parser("funds", help="browse/screen all fund categories")
    s.add_argument("--category", help="category id or name (see categories)")
    s.add_argument("--group", choices=["EQUITY", "DEBT", "HYBRID", "COMMODITIES", "OTHERS"])
    s.add_argument("--duration", choices=["1m", "3m", "6m", "1y", "3y", "5y", "10y"], default="1y")
    s.add_argument("--mode", choices=["sip", "lumpsum"], default="lumpsum")
    s.add_argument("--sort-by", choices=["etm_rank", "returns", "fund_size"], default="returns")
    s.add_argument("--order", choices=["asc", "desc"], default="desc")
    s.add_argument("--page", type=int, default=0)
    s.add_argument("--size", type=int, default=20)

    s = sub.add_parser("fund", help="fund report card by scheme id")
    s.add_argument("scheme_id")
    s.add_argument("--full", action="store_true")

    s = sub.add_parser("compare", help="compare 2..4 funds")
    s.add_argument("scheme_ids", help="comma separated ids")

    sub.add_parser("categories", help="all fund categories with ids")

    s = sub.add_parser("featured", help="ET Money curated theme lists")
    s.add_argument("theme", help=", ".join(sorted(THEMES)))

    s = sub.add_parser("stocks", help="market screens")
    s.add_argument("screen", choices=sorted(SCREENS))
    s.add_argument("--limit", type=int, default=25)

    s = sub.add_parser("index", help="index constituents")
    s.add_argument("key")
    s.add_argument("--limit", type=int, default=50)

    s = sub.add_parser("sector", help="sector constituents")
    s.add_argument("key")
    s.add_argument("--limit", type=int, default=50)

    s = sub.add_parser("stock", help="stock overview by id or slug/id")
    s.add_argument("stock_ref")
    s.add_argument("--full", action="store_true")

    sub.add_parser("status", help="check upstream reachability")

    return p


TOOL_SUMMARY = [
    ("mf_search", "find funds by name"),
    ("mf_list", "screen all 67 fund categories"),
    ("mf_detail", "full fund report card"),
    ("mf_compare", "side-by-side 2-4 funds"),
    ("mf_categories", "category id reference"),
    ("mf_featured", "curated best-of lists"),
    ("stock_screen", "gainers/losers/52w/multibagger screens"),
    ("index_stocks", "NIFTY index constituents"),
    ("sector_stocks", "sector constituents"),
    ("stock_detail", "stock price, returns, peers"),
]


def show_home_view() -> None:
    """AXI §8: content-first home view, zero network calls (humans only)."""
    print(_toon_kv("name", "etmoney-lyr"))
    print(_toon_kv("version", __version__))
    print(_toon_kv("what", "ET Money research layer: mutual funds + Indian stocks"))
    print(_toon_kv("transport", "stdio MCP server when run bare inside mcp config"))
    print()
    print("quick start:")
    q = 'etmoney-lyr search "parag parikh"'
    print(f"  {_toon_kv('1', q)}")
    print(f"  {_toon_kv('2', 'etmoney-lyr fund 19230 --full')}")
    print(f"  {_toon_kv('3', 'etmoney-lyr funds --category flexicap')}")
    print(f"  {_toon_kv('4', 'etmoney-lyr stocks top_gainers')}")
    print()
    print("next steps:")
    print(_toon_kv("mcp_config", '{"mcpServers":{"etmoney":{"command":"etmoney-lyr"}}}'))
    print(_toon_kv("list_tools", "etmoney-lyr --list-tools"))


def _run_mcp_server() -> None:
    """Piped stdin = an MCP client speaking JSON-RPC: serve, silently."""
    import os

    # AXI §1: clean stdout for the protocol; stderr is pure noise to agents.
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, sys.stderr.fileno())
    os.close(devnull_fd)
    from etmoney_lyr.server import create_mcp_server

    create_mcp_server().run()


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    as_json = getattr(args, "json", False)

    if args.list_tools:
        rows = []
        for name, desc in TOOL_SUMMARY:
            if args.fields and args.fields.lower() not in name.lower():
                continue
            rows.append({"tool": name, "description": desc})
        _out({"tools": len(rows)}, as_json)
        print()
        _out(rows, as_json)
        return

    # Bare invocation: humans (TTY) get the home view; MCP clients (piped
    # stdin) get the stdio server — one binary, both modes (family convention).
    if args.cmd is None:
        if sys.stdin.isatty():
            show_home_view()
        else:
            _run_mcp_server()
        return

    handlers = {
        "search": lambda: run_search(args, as_json),
        "funds": lambda: run_funds(args, as_json),
        "fund": lambda: run_fund(args, as_json),
        "compare": lambda: run_compare(args, as_json),
        "categories": lambda: run_categories(as_json),
        "featured": lambda: run_featured(args, as_json),
        "stocks": lambda: run_stocks(args, as_json),
        "index": lambda: run_listing_page("index", args.key, args.limit, as_json),
        "sector": lambda: run_listing_page("sector", args.key, args.limit, as_json),
        "stock": lambda: run_stock_detail(args, as_json),
    }

    if args.cmd == "status":
        asyncio.run(run_status())
        return

    handler = handlers.get(args.cmd)
    if handler is None:
        axi_error(f"unknown command '{args.cmd}'", hint="run `etmoney-lyr` for the command list")
        return
    try:
        asyncio.run(handler())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
