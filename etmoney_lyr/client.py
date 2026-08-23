"""Async HTTP client for etmoney.com with polite rate limiting and retries."""

import asyncio
import time

import httpx

from etmoney_lyr.constants import (
    BASE_URL,
    LISTING_API,
    SEARCH_API,
    USER_AGENT,
)
from etmoney_lyr.exceptions import NotFoundError, UpstreamError
from etmoney_lyr.logging_config import logger

# ponytail: global lock — one agent at a time; per-host locks if throughput ever matters
_RATE_LOCK = asyncio.Lock()
_MIN_INTERVAL = 0.5  # seconds between upstream requests
_MAX_RETRIES = 2  # extra attempts on 5xx / transport errors


def _backoff_delay(attempt: int) -> float:
    """Retry wait after the Nth failed attempt (0-based). Patchable in tests."""
    return 1.5 * (attempt + 1)


class EtMoneyClient:
    """Single shared async client. Create one per process (FastMCP lifespan or CLI run)."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 20.0, transport=None):
        self._client = httpx.AsyncClient(
            transport=transport,
            base_url=base_url,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            timeout=timeout,
            follow_redirects=True,
        )
        self._last_request_ts = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _throttle(self) -> None:
        async with _RATE_LOCK:
            wait = _MIN_INTERVAL - (time.monotonic() - self._last_request_ts)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_ts = time.monotonic()

    async def request(self, path: str, *, params: dict | None = None) -> httpx.Response:
        """GET with throttle + bounded retries. Raises UpstreamError/NotFoundError."""
        last_exc: Exception | None = None
        for attempt in range(1 + _MAX_RETRIES):
            await self._throttle()
            try:
                resp = await self._client.get(path, params=params)
            except httpx.TimeoutException as e:
                last_exc = e
                logger.warning("timeout on %s (attempt %d)", path, attempt + 1)
                continue
            except httpx.HTTPError as e:
                raise UpstreamError(f"request failed: {path}", hint=str(e)) from e

            if resp.status_code == 404:
                raise NotFoundError(f"not found upstream: {path}")
            if resp.status_code in (429, 500, 502, 503, 504):
                last_exc = UpstreamError(
                    f"upstream unavailable ({resp.status_code}): {path}",
                    hint="ET Money may be rate limiting; retry shortly",
                )
                logger.warning("%s -> %d (attempt %d)", path, resp.status_code, attempt + 1)
                await asyncio.sleep(_backoff_delay(attempt))
                continue
            if resp.is_error:
                raise UpstreamError(f"upstream error {resp.status_code}: {path}")
            return resp
        raise last_exc or UpstreamError(f"request failed: {path}")

    async def get_json(self, path: str, *, params: dict | None = None) -> dict:
        resp = await self.request(path, params=params)
        try:
            data = resp.json()
        except ValueError as e:
            raise UpstreamError("upstream returned invalid JSON", hint=path[:120]) from e
        if not isinstance(data, dict):
            raise UpstreamError("unexpected response shape (not a JSON object)")
        return data

    async def get_html(self, path: str, *, params: dict | None = None) -> str:
        resp = await self.request(path, params=params)
        if not resp.text.strip():
            raise UpstreamError("upstream returned an empty page", hint=path[:120])
        return resp.text

    # ── high-level fetchers ────────────────────────────────────────────────

    async def fund_listing_raw(self, **params) -> dict:
        return await self.get_json(LISTING_API, params=params)

    async def search_funds_raw(self, term: str) -> dict:
        return await self.get_json(SEARCH_API + term.strip())
