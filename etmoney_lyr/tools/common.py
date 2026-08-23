"""Shared plumbing for tool modules: lazy client + uniform error handling."""

from functools import lru_cache

from etmoney_lyr.client import EtMoneyClient
from etmoney_lyr.exceptions import (
    EtmoneyError,
    NotFoundError,
    UpstreamError,
    ValidationError,
)


@lru_cache(maxsize=1)
def get_client() -> EtMoneyClient:
    # ponytail: process-wide singleton; FastMCP runs one event loop per process
    return EtMoneyClient()


def handle_api_error(e: Exception) -> dict:
    """Convert exceptions into structured dicts; never raises for expected errors.

    Returns {"ok": False, ...} shape so agents always get machine-readable errors.
    Unexpected exception types re-raise.
    """
    if isinstance(e, NotFoundError):
        return {"ok": False, "error": "not_found", "message": e.msg, "hint": e.hint}
    if isinstance(e, ValidationError):
        return {"ok": False, "error": "validation", "message": e.msg, "hint": e.hint}
    if isinstance(e, UpstreamError):
        return {"ok": False, "error": "upstream_error", "message": e.msg, "hint": e.hint}
    if isinstance(e, EtmoneyError):
        return {"ok": False, "error": "request_error", "message": e.msg, "hint": e.hint}
    raise e
