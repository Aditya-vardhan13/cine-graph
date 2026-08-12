"""Source-access controls shared by all collection adapters.

API adapters follow their published API policy and rate limits. HTML crawlers must
obtain and obey robots.txt before requesting a content URL; an unavailable or
ambiguous robots policy is treated as disallow-by-default.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx


class SourceAccessDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    robots_url: str
    reason: str


def robots_decision(url: str, user_agent: str, client: httpx.Client | None = None) -> AccessDecision:
    """Return a fail-closed robots decision for an HTML page URL."""
    parsed = urlparse(url)
    robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
    owns_client = client is None
    client = client or httpx.Client(timeout=20, headers={"User-Agent": user_agent})
    try:
        response = client.get(robots_url)
        if response.status_code != 200:
            return AccessDecision(False, robots_url, f"robots.txt returned HTTP {response.status_code}")
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        allowed = parser.can_fetch(user_agent, url)
        return AccessDecision(allowed, robots_url, "allowed by robots.txt" if allowed else "disallowed by robots.txt")
    except httpx.HTTPError as exc:
        return AccessDecision(False, robots_url, f"robots.txt could not be retrieved: {exc}")
    finally:
        if owns_client:
            client.close()


def require_robots_permission(url: str, user_agent: str) -> AccessDecision:
    decision = robots_decision(url, user_agent)
    if not decision.allowed:
        raise SourceAccessDenied(f"Refusing to fetch {url}: {decision.reason} ({decision.robots_url})")
    return decision
