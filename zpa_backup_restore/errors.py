"""Shared expected errors for CLI and API layers."""


class CliError(Exception):
    """Expected user-facing error without a traceback."""


class ApiError(CliError):
    """Normalized non-success response from a ZPA API call."""

    def __init__(self, method: str, url: str, status: int, body: str) -> None:
        self.method = method
        self.url = url
        self.status = status
        self.body = body
        super().__init__(f"{method} {url} failed with HTTP {status}: {body}")
