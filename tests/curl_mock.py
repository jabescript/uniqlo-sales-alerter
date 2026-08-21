"""A minimal respx-like router for mocking curl_cffi.requests.AsyncSession.get.

``respx`` only intercepts ``httpx``; since :class:`UniqloClient` now uses
``curl_cffi`` directly, this module provides just enough of the same API
(``curl_mock.get(url).mock(...)`` / ``.side_effect = [...]``, used as a
decorator or context manager) so tests keep the same shape.
"""

from __future__ import annotations

import functools
import json as json_mod
from copy import copy
from typing import Any
from unittest.mock import patch
from urllib.parse import urlencode

from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError


class FakeHeaders(dict):
    """Case-insensitive header mapping, mirroring curl_cffi/httpx Headers."""

    def __init__(self, data: dict[str, str] | None = None) -> None:
        super().__init__()
        for key, value in (data or {}).items():
            self[key] = value

    def __setitem__(self, key: str, value: str) -> None:
        super().__setitem__(key.lower(), value)

    def __getitem__(self, key: str) -> str:
        return super().__getitem__(key.lower())

    def get(self, key: str, default: Any = None) -> Any:
        return super().get(key.lower(), default)


class FakeRequest:
    def __init__(self, url: str, headers: dict[str, str]) -> None:
        self.url = url
        self.headers = FakeHeaders(headers)


class FakeResponse:
    """Stand-in for a :class:`curl_cffi.requests.Response`."""

    def __init__(
        self,
        status_code: int = 200,
        *,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = FakeHeaders(headers)
        self._json = json
        self.text = json_mod.dumps(json) if json is not None else ""
        self.request: FakeRequest | None = None

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise CurlHTTPError(f"HTTP Error {self.status_code}", 0, self)


class Route:
    """A registered URL and its queued/fixed mock response(s)."""

    def __init__(self, url: str) -> None:
        self.url = url
        self._fixed: FakeResponse | None = None
        self._queue: list[FakeResponse] | None = None
        self.calls: list[FakeResponse] = []

    def mock(self, return_value: FakeResponse) -> "Route":
        self._fixed = return_value
        return self

    @property
    def side_effect(self) -> list[FakeResponse] | None:
        return self._queue

    @side_effect.setter
    def side_effect(self, responses: list[FakeResponse]) -> None:
        self._queue = list(responses)

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def called(self) -> bool:
        return bool(self.calls)

    def _next_response(self) -> FakeResponse:
        if self._queue:
            resp = self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]
            return copy(resp)
        if self._fixed is not None:
            # Return a copy so each call gets its own `.request` (the fixed
            # response instance is shared across every call to this route).
            return copy(self._fixed)
        raise AssertionError(f"curl_mock: no response registered for {self.url}")


class CurlMockRouter:
    """Patches ``AsyncSession.get`` to serve responses from registered routes."""

    def __init__(self) -> None:
        self._routes: dict[str, Route] = {}
        self._patcher: Any = None

    def get(self, url: str) -> Route:
        return self._routes.setdefault(url, Route(url))

    def reset(self) -> None:
        self._routes.clear()

    def __call__(self, func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            with self:
                return await func(*args, **kwargs)
        return wrapper

    def __enter__(self) -> "CurlMockRouter":
        self.reset()
        router = self

        async def fake_get(
            session: AsyncSession, url: str, *, params: dict[str, str] | None = None,
            **_kwargs: Any,
        ) -> FakeResponse:
            route = router._routes.get(url)
            if route is None:
                raise AssertionError(f"curl_mock: no route registered for GET {url}")
            resp = route._next_response()
            full_url = f"{url}?{urlencode(params)}" if params else url
            resp.request = FakeRequest(full_url, dict(session.headers))
            route.calls.append(resp)
            return resp

        self._patcher = patch.object(AsyncSession, "get", new=fake_get)
        self._patcher.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._patcher is not None:
            self._patcher.stop()
            self._patcher = None


curl_mock = CurlMockRouter()
