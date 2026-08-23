# AGENTS.md

Guidance for AI agents working on this repository.

## Development Commands

- `uv sync --dev`
- Lint: `uv run ruff check .` (auto-fix `--fix`; format: `uv run ruff format .`)
- Tests: `uv run pytest`
- CLI locally: `uv run etmoney-lyr --help`, home view: bare invocation
- Server locally: `uv run python -m etmoney_lyr`

## Architecture

One platform layer, three data paths (do not mix concerns):

1. **JSON APIs** (`client.py` → listing/search): stable, typed payloads.
   Listing params must match the site's JS contract exactly:
   `categoryId, returnConsistensy, vroRating, fundSize, fundHouse, duration,
   investmentMode, sortType, sortOrder, size, page`. Null/undefined params are
   OMITTED (the site's URL builder skips them; sending them 500s).
2. **SSR HTML + embedded JS DTOs** (`parsers/funds.py`): fund detail/compare/
   featured pages embed full JSON in `var NAME = {...}` blocks. Parse the DTOs,
   not the HTML tables, wherever a DTO exists (`compSchemeDTO`,
   `mfPeerSchemesDTO`, `schemeComparisionTileDtoList`, ...). HTML parsing is
   only for the overview table / trailing returns / managers accordion.
3. **Next.js RSC flight payloads** (`jsvars.py` + `parsers/stocks.py`): stock
   pages embed `self.__next_f.push([1,"..."])` chunks. Reassemble, then extract
   balanced JSON values by key (`find_value` for collections like `stockList`,
   `find_json_objects` for object containment).

URL trick: `/mutual-funds/<any-slug>/<valid-id>` redirects to canonical slug;
invalid id 404s. Same pattern assumed for stocks.

## Conventions (family: reddit-lyr/swiggy-lyr/twitter-lyr)

- Tool logic = module-level async functions in `tools/`; `register_*_tools(mcp)`
  wraps them for FastMCP. Tests/CLI call the plain functions directly.
- Every tool returns `{"ok": true/false, ...}` — errors go through
  `handle_api_error` (maps NotFound/Validation/Upstream; re-raises unexpected).
- CLI: TOON output default, `--json` escape hatch, structured errors exit 2,
  home view makes zero network calls.
- Parser fixtures live in `tests/fixtures/` captured from live pages. When the
  site's markup changes, fixtures fail loudly — recapture, fix parser, commit both.

## Release Process

CI runs on every push/PR: ruff check + format + pytest (py3.11–3.13) + build sanity.
Tagging `vX.Y.Z` triggers CI → `uv build` → PyPI publish (trusted publishing,
`pypi` environment must be configured in the GitHub repo settings).

```bash
uv version --bump patch          # update pyproject AND uv.lock if present
uv run ruff check . && uv run pytest
git commit -am "chore(release): v0.1.x" && git tag v0.1.x && git push origin main v0.1.x
```

Users install from anywhere:
- one-line script → `curl -sSL .../install.sh | bash`
- `uv tool install git+https://github.com/ishan-parihar/etmoney-lyr.git`
- `uv tool install etmoney-lyr` (after first PyPI publish)

Conventional commits: `feat(scope): subject` (<50 chars).

## Binary modes (do not break this)

Bare `etmoney-lyr` is dual-mode via TTY detection (reddit-lyr pattern):
- interactive terminal → AXI home view (zero network)
- piped stdin → stdio MCP server with stderr silenced

Tests monkeypatch `sys.stdin.isatty`; never remove the branch.
