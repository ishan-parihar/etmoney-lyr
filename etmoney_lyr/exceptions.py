"""Exception hierarchy for etmoney-lyr."""


class EtmoneyError(Exception):
    """Base error with optional structured hint (AXI-style)."""

    def __init__(self, msg: str, hint: str | None = None):
        super().__init__(msg)
        self.msg = msg
        self.hint = hint


class UpstreamError(EtmoneyError):
    """ET Money returned an unexpected/failed response."""


class NotFoundError(EtmoneyError):
    """Requested entity does not exist upstream."""


class ValidationError(EtmoneyError):
    """Caller-supplied parameters are invalid."""
