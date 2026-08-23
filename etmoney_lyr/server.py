"""FastMCP server factory for etmoney-lyr."""

from fastmcp import FastMCP

from etmoney_lyr.tools import register_all_tools

SERVER_NAME = "etmoney-lyr"

INSTRUCTIONS = """ET Money research layer for Indian markets — read-only, no transactions.

Mutual funds (all 67 categories: equity, debt, hybrid, gold/silver commodities,
index funds, FoF, sectoral, retirement, international):
- mf_search: find funds by name → get scheme_id
- mf_list: browse/screen any category with sort + duration filters
- mf_detail: full report card by scheme_id (holdings, ratios, peers)
- mf_compare: side-by-side 2–4 funds
- mf_categories: list all category ids
- mf_featured: curated lists (best SIP funds, gold funds, ...)

Stocks:
- stock_screen: gainers/losers/52w extremes/multibagger/bluechip screens
- index_stocks / sector_stocks: constituents of NIFTY indices and sectors
- stock_detail: price, returns across horizons, peer fundamentals by stock id

Typical flow: mf_search("parag parikh") → mf_detail(scheme_id) → mf_compare([id1,id2]).
All data is sourced from public etmoney.com pages; research only."""


def create_mcp_server() -> FastMCP:
    mcp = FastMCP(
        SERVER_NAME,
        instructions=INSTRUCTIONS,
    )
    count = register_all_tools(mcp)
    if count == 0:
        from etmoney_lyr.exceptions import UpstreamError

        raise UpstreamError("no tools registered — installation is broken")
    return mcp


def run(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
    mcp = create_mcp_server()
    if transport in ("http", "streamable-http"):
        mcp.run(transport="http", host=host, port=port)
    else:
        mcp.run()


if __name__ == "__main__":
    run()
