"""Server factory tests: tool registration completeness."""

import pytest

from etmoney_lyr.server import INSTRUCTIONS, create_mcp_server

EXPECTED_TOOLS = {
    "mf_search",
    "mf_list",
    "mf_detail",
    "mf_compare",
    "mf_categories",
    "mf_featured",
    "stock_screen",
    "index_stocks",
    "sector_stocks",
    "stock_detail",
}


@pytest.fixture(scope="module")
def tools():
    import asyncio

    mcp = create_mcp_server()
    tm = getattr(mcp, "_tool_manager", None)
    if tm is not None:
        raw = tm.get_tools()
        raw = raw.values() if isinstance(raw, dict) else raw
        return {t.name for t in raw}

    async def _names():
        return {t.name for t in await mcp.list_tools()}

    return asyncio.run(_names())


def test_all_ten_tools_registered(tools):
    assert tools == EXPECTED_TOOLS


def test_instructions_mention_key_flows(tools):
    assert "scheme_id" in INSTRUCTIONS
    assert "research" in INSTRUCTIONS.lower()
