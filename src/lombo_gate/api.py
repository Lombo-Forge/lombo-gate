"""The Seerr and Sonarr calls, standard library only. Both take the key in X-Api-Key.

Every failure becomes an ApiError with a short message, so callers print it instead of crashing.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

PAGE, MAX_PAGES = 100, 20


class ApiError(Exception):
    """A request failed. The message names the service, the path and the reason."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would turn a redirected POST into a GET (nothing approved, no error) and resend the key."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_opener = urllib.request.build_opener(_NoRedirect)


class Api:
    def __init__(self, name: str, base_url: str, api_key: str, timeout: float = 10):
        self.name = name
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.timeout = timeout

    def _call(self, path: str, method: str = "GET") -> bytes:
        # S310 is silenced: config.py only accepts http(s) URLs.
        req = urllib.request.Request(self.base + path, method=method, headers={"X-Api-Key": self.key})  # noqa: S310
        try:
            with _opener.open(req, timeout=self.timeout) as resp:
                return bytes(resp.read())
        except urllib.error.HTTPError as e:
            raise ApiError(f"{self.name} {path}: HTTP {e.code}") from e
        except (urllib.error.URLError, OSError) as e:
            raise ApiError(f"{self.name} {path}: {e}") from e

    def get(self, path: str) -> Any:
        try:
            return json.loads(self._call(path))
        except ValueError as e:
            raise ApiError(f"{self.name} {path}: not JSON (is the URL right?)") from e

    def post(self, path: str) -> None:
        self._call(path, "POST")


def _pages(seerr: Api, path: str, **query: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in range(MAX_PAGES):
        q = urllib.parse.urlencode({**query, "take": PAGE, "skip": page * PAGE})
        rows = seerr.get(f"{path}?{q}").get("results", [])
        out.extend(rows)
        if len(rows) < PAGE:
            break
    return out


def pending_requests(seerr: Api) -> list[dict[str, Any]]:
    """Oldest first."""
    return _pages(seerr, "/api/v1/request", filter="pending", sort="added", sortDirection="asc")


def users(seerr: Api) -> list[dict[str, Any]]:
    return _pages(seerr, "/api/v1/user")
