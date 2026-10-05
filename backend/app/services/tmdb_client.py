"""Conservative TMDb developer-API client for local, non-commercial research.

Requests are deliberately serial. The client never puts credentials in a URL,
accepts an arbitrary URL, or prints the bearer token in errors.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


API_ROOT = "https://api.themoviedb.org/3"
CLIENT_VERSION = "tmdb-v3-local-v1"


class TmdbAccessError(RuntimeError):
    pass


def bearer_token(path: Path) -> str:
    if not path.is_file():
        raise TmdbAccessError("TMDb credential file is missing")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    token = values.get("API_ Read_Access_Token", "") or values.get("TMDB_READ_ACCESS_TOKEN", "")
    if not token:
        raise TmdbAccessError("TMDb read-access token is missing")
    return token


class TmdbClient:
    def __init__(self, token: str, *, min_interval: float = 0.6, timeout: float = 25):
        if not token:
            raise TmdbAccessError("TMDb read-access token is missing")
        self._client = httpx.Client(
            base_url=API_ROOT,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                     "User-Agent": "CineGraph-local-research/0.1"},
            timeout=timeout,
            follow_redirects=False,
        )
        self.min_interval = min_interval
        self._last_request = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TmdbClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not path.startswith("/") or "//" in path or ".." in path:
            raise ValueError("TMDb path must be an internal documented endpoint")
        for attempt in range(4):
            delay = self.min_interval - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            try:
                response = self._client.get(path, params=params)
            except httpx.RequestError as exc:
                if attempt == 3:
                    raise TmdbAccessError(f"TMDb transport failed after retries: {type(exc).__name__}") from None
                time.sleep(min(15.0, 2.0 ** attempt))
                continue
            self._last_request = time.monotonic()
            if response.status_code in {401, 403}:
                raise TmdbAccessError(f"TMDb denied access ({response.status_code}); stopping")
            if response.status_code == 429:
                retry = response.headers.get("Retry-After", "")
                try:
                    seconds = min(120.0, max(1.0, float(retry)))
                except ValueError:
                    seconds = min(30.0, 2.0 ** attempt)
                if attempt == 3:
                    raise TmdbAccessError("TMDb rate limited the request after retries")
                time.sleep(seconds)
                continue
            if response.status_code in {500, 502, 503, 504} and attempt < 3:
                time.sleep(min(15.0, 2.0 ** attempt))
                continue
            if response.status_code != 200:
                raise TmdbAccessError(f"TMDb returned HTTP {response.status_code}")
            payload = response.json()
            if not isinstance(payload, dict):
                raise TmdbAccessError("TMDb returned a non-object payload")
            return payload
        raise TmdbAccessError("TMDb request failed")

    def find_imdb(self, tconst: str) -> list[dict[str, Any]]:
        if not tconst.startswith("tt") or not tconst[2:].isdigit():
            raise ValueError("Invalid IMDb title ID")
        payload = self._get(f"/find/{quote(tconst)}", {"external_source": "imdb_id", "language": "en-US"})
        return [value for value in payload.get("movie_results", []) if isinstance(value, dict)]

    def search_movie(self, title: str, year: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"query": title, "include_adult": "false", "language": "en-US"}
        if year is not None:
            params["year"] = year
        payload = self._get("/search/movie", params)
        return [value for value in payload.get("results", []) if isinstance(value, dict)]

    def movie_bundle(self, movie_id: int) -> dict[str, Any]:
        if movie_id <= 0:
            raise ValueError("Invalid TMDb movie ID")
        return self._get(
            f"/movie/{movie_id}",
            {"language": "en-US", "append_to_response":
             "credits,release_dates,external_ids,keywords,alternative_titles,translations"},
        )
