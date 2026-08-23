---
name: etmoney-mcp
description: >
  Research Indian mutual funds and stocks via MCP. All 67 fund categories
  (equity, debt, hybrid, gold, index, FoF), stock screens, NIFTY index
  constituents — from public ET Money data, no login required.
---

# ET Money MCP Skill

Read-only research layer over etmoney.com: mutual funds (all categories) +
Indian stock market screens.

<!-- Install: npx skills add ishan-parihar/etmoney-lyr --skill etmoney-mcp -->

## Quick Start

```bash
etmoney-lyr            # stdio MCP server
```

## MCP Configuration

```json
{
  "mcpServers": {
    "etmoney": {
      "command": "etmoney-lyr",
      "args": []
    }
  }
}
```

## Key Tools (10 total)

| Tool | Description |
|------|-------------|
| `mf_search` | Find funds by name → scheme ids |
| `mf_list` | Screen all 67 categories with sort/duration filters |
| `mf_detail` | Full fund report card by scheme id |
| `mf_compare` | Side-by-side 2–4 funds |
| `mf_categories` | Category id reference |
| `mf_featured` | Curated best-of lists |
| `stock_screen` | Gainers/losers/52w extremes/multibagger screens |
| `index_stocks` | NIFTY index constituents |
| `sector_stocks` | Sector constituents |
| `stock_detail` | Stock price, returns across horizons, peers |

## Typical Research Flow

1. `mf_search(query="parag parikh")` → get `scheme_id`
2. `mf_detail(scheme_id=19230)` → holdings, ratios, peers
3. `mf_compare(scheme_ids=[19230, 25643])` → side-by-side verdict inputs

For screening: `mf_list(category="small cap", duration="5y", sort_by="returns")`.
Category names are fuzzy-matched; call `mf_categories` when unsure.

## Notes

- No authentication needed; research data only (no orders/KYC).
- `etm_rank: -1` means the fund is unranked upstream.
- Returns keys are day-windows: `30`=1M, `365`=1Y, `1825`=5Y...
