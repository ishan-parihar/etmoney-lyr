FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY etmoney_lyr ./etmoney_lyr

RUN uv venv && uv pip install --no-cache .

# stdio MCP server; override with `docker run ... etmoney-lyr --json search x` for CLI use
ENTRYPOINT ["/app/.venv/bin/etmoney-lyr"]
