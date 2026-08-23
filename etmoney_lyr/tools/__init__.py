"""Tool registration for all etmoney-lyr modules."""

from fastmcp import FastMCP

from etmoney_lyr.tools.funds import register_fund_tools
from etmoney_lyr.tools.stocks import register_stock_tools


def register_all_tools(mcp: FastMCP) -> int:
    return register_fund_tools(mcp) + register_stock_tools(mcp)
