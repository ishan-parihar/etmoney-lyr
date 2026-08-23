"""Client tests with mocked transport: retries, errors, throttling."""

import time

import httpx
import pytest

import etmoney_lyr.client as client_mod
from etmoney_lyr.client import EtMoneyClient
from etmoney_lyr.exceptions import NotFoundError, UpstreamError


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    # speed: zero throttle gap + zero retry backoff (real asyncio.sleep kept,
    # so the throttle test below can still measure real elapsed time)
    monkeypatch.setattr(client_mod, "_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(client_mod, "_backoff_delay", lambda attempt: 0.0)


async def test_get_json_ok():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"ok": 1})

    c = EtMoneyClient(transport=_transport(handler))
    try:
        assert await c.get_json("/api/x") == {"ok": 1}
        assert calls == ["/api/x"]
    finally:
        await c.aclose()


async def test_get_json_invalid_body_raises():
    def handler(request):
        return httpx.Response(200, text="<html>not json</html>")

    c = EtMoneyClient(transport=_transport(handler))
    try:
        with pytest.raises(UpstreamError, match="invalid JSON"):
            await c.get_json("/api/x")
    finally:
        await c.aclose()


async def test_get_json_non_dict_raises():
    def handler(request):
        return httpx.Response(200, json=[1, 2])

    c = EtMoneyClient(transport=_transport(handler))
    try:
        with pytest.raises(UpstreamError, match="not a JSON object"):
            await c.get_json("/api/x")
    finally:
        await c.aclose()


async def test_404_raises_not_found_no_retry():
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(404)

    c = EtMoneyClient(transport=_transport(handler))
    try:
        with pytest.raises(NotFoundError):
            await c.request("/mutual-funds/nope/999")
        assert count == 1, "404 must not be retried"
    finally:
        await c.aclose()


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_server_errors_retry_then_raise(status, monkeypatch):
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(status)

    c = EtMoneyClient(transport=_transport(handler))
    try:
        with pytest.raises(UpstreamError, match=str(status)):
            await c.request("/x")
        assert len(attempts) == 3, "1 initial + 2 retries"
    finally:
        await c.aclose()


async def test_server_error_recovers_on_second_attempt():
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"recovered": True})

    c = EtMoneyClient(transport=_transport(handler))
    try:
        data = await c.get_json("/flaky")
        assert data == {"recovered": True}
    finally:
        await c.aclose()


async def test_timeout_retries_then_raises(monkeypatch):
    attempts = []

    def handler(request):
        attempts.append(1)
        raise httpx.ConnectTimeout("boom", request=request)

    c = EtMoneyClient(transport=_transport(handler))
    try:
        with pytest.raises((UpstreamError, httpx.TimeoutException)):
            await c.request("/slow")
        assert len(attempts) >= 3
    finally:
        await c.aclose()


async def test_empty_html_raises():
    def handler(request):
        return httpx.Response(200, text="   ")

    c = EtMoneyClient(transport=_transport(handler))
    try:
        with pytest.raises(UpstreamError, match="empty page"):
            await c.get_html("/x")
    finally:
        await c.aclose()


async def test_throttle_enforces_interval(monkeypatch):
    monkeypatch.setattr(client_mod, "_MIN_INTERVAL", 0.05)
    seen = []

    def handler(request):
        seen.append(time.monotonic())
        return httpx.Response(200, text="ok")

    c = EtMoneyClient(transport=_transport(handler))
    try:
        await c.get_html("/a")
        await c.get_html("/b")
    finally:
        await c.aclose()
    assert len(seen) == 2
    assert seen[1] - seen[0] >= 0.035  # allow event-loop jitter


async def test_search_term_is_path_appended_and_stripped():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"mfBasicDetailList": []})

    c = EtMoneyClient(transport=_transport(handler))
    try:
        await c.search_funds_raw("  parag parikh  ")
    finally:
        await c.aclose()
    assert "mf-search/parag%20parikh" in captured["url"]


async def test_follows_redirect_for_fund_pages():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/fund/19230"):
            return httpx.Response(301, headers={"location": "/mutual-funds/real-slug/19230"})
        return httpx.Response(200, text="<html><body><h1>Fund</h1></body></html>")

    c = EtMoneyClient(transport=_transport(handler))
    try:
        html = await c.get_html("/mutual-funds/fund/19230")
        assert "<h1>Fund</h1>" in html
    finally:
        await c.aclose()
