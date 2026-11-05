"""Strict, sequential HTTP capture for ordinary English Wikipedia article URLs."""
from __future__ import annotations

from hashlib import sha256
from time import monotonic, sleep
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.services.wikipedia_article_html import MAX_HTML_BYTES, ArticlePageUrlError, validate_article_url


ROBOTS_URL = "https://en.wikipedia.org/robots.txt"
MAX_REDIRECTS = 5


class WikipediaCaptureError(RuntimeError):
    """Capture stopped because the source response was unsafe or unusable."""


class WikipediaArticleFetcher:
    """A single-job client that loads robots once and paces every HTTP request."""

    def __init__(self, *, user_agent: str, interval_seconds: float = 1.0,
                 timeout_seconds: float = 30.0) -> None:
        if not user_agent.strip():
            raise ValueError("A descriptive user-agent is required.")
        if not 1.0 <= interval_seconds <= 10.0:
            raise ValueError("Wikipedia article requests must be at least one second apart.")
        self.user_agent = user_agent
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.client: httpx.Client | None = None
        self._robots: RobotFileParser | None = None
        self._last_request_started: float | None = None
        self.robots_sha256: str | None = None

    def __enter__(self) -> "WikipediaArticleFetcher":
        self.client = httpx.Client(timeout=self.timeout_seconds, follow_redirects=False,
                                   headers={"User-Agent": self.user_agent,
                                            "Accept": "text/html,application/xhtml+xml"})
        try:
            response = self._get(ROBOTS_URL)
        except httpx.HTTPError as exc:
            self.client.close()
            raise WikipediaCaptureError(f"Could not retrieve Wikipedia robots.txt: {exc}") from exc
        if response.status_code != 200:
            self.client.close()
            raise WikipediaCaptureError(f"Wikipedia robots.txt returned HTTP {response.status_code}; refusing capture.")
        body = response.content
        if len(body) > 512 * 1024:
            self.client.close()
            raise WikipediaCaptureError("Wikipedia robots.txt exceeded the 512 KiB safety limit.")
        self.robots_sha256 = sha256(body).hexdigest()
        parser = RobotFileParser(ROBOTS_URL)
        parser.parse(response.text.splitlines())
        self._robots = parser
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def _pace(self) -> None:
        if self._last_request_started is not None:
            remaining = self.interval_seconds - (monotonic() - self._last_request_started)
            if remaining > 0:
                sleep(remaining)
        self._last_request_started = monotonic()

    def _get(self, url: str) -> httpx.Response:
        if self.client is None:
            raise WikipediaCaptureError("WikipediaArticleFetcher must be used as a context manager.")
        self._pace()
        return self.client.get(url)

    def _get_article(self, url: str) -> tuple[int, dict[str, str], bytes]:
        if self.client is None:
            raise WikipediaCaptureError("WikipediaArticleFetcher must be used as a context manager.")
        self._pace()
        with self.client.stream("GET", url) as response:
            headers = dict(response.headers)
            if response.status_code != 200:
                return response.status_code, headers, b""
            body = bytearray()
            for block in response.iter_bytes():
                body.extend(block)
                if len(body) > MAX_HTML_BYTES:
                    raise WikipediaCaptureError("Wikipedia article exceeded the 15 MiB response limit.")
            return response.status_code, headers, bytes(body)

    def fetch(self, url: str) -> tuple[bytes, str, int, str]:
        """Fetch one article, checking robots before each request and redirect."""
        if self._robots is None:
            raise WikipediaCaptureError("robots.txt has not been loaded for this capture job.")
        try:
            current = validate_article_url(url)
        except ArticlePageUrlError as exc:
            raise WikipediaCaptureError(str(exc)) from exc
        for redirect_count in range(MAX_REDIRECTS + 1):
            if not self._robots.can_fetch(self.user_agent, current):
                raise WikipediaCaptureError(f"robots.txt disallows article URL: {current}")
            try:
                status, headers, body = self._get_article(current)
            except httpx.HTTPError as exc:
                raise WikipediaCaptureError(f"Wikipedia request failed: {exc}") from exc
            if status in {301, 302, 303, 307, 308}:
                if redirect_count == MAX_REDIRECTS:
                    raise WikipediaCaptureError("Wikipedia article exceeded the redirect limit.")
                location = headers.get("location")
                if not location:
                    raise WikipediaCaptureError("Wikipedia returned a redirect without a Location header.")
                try:
                    current = validate_article_url(urljoin(current, location))
                except ArticlePageUrlError as exc:
                    raise WikipediaCaptureError(f"Wikipedia redirected outside the allowed article route: {location}") from exc
                continue
            if status in {401, 403, 429}:
                raise WikipediaCaptureError(
                    f"Wikipedia returned HTTP {status}; capture stopped without retry."
                )
            if status == 404:
                raise FileNotFoundError(f"Wikipedia article not found: {current}")
            if status != 200:
                raise WikipediaCaptureError(f"Wikipedia returned HTTP {status}; capture stopped.")
            media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if media_type not in {"text/html", "application/xhtml+xml"}:
                raise WikipediaCaptureError(f"Expected an HTML page, received {media_type or 'unknown media type'}.")
            return body, current, status, media_type
        raise WikipediaCaptureError("Wikipedia redirect resolution terminated unexpectedly.")
