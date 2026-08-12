import httpx

from app.services.compliance import robots_decision


class FakeClient:
    def __init__(self, status_code: int, body: str):
        self.response = httpx.Response(status_code, text=body)

    def get(self, _url: str) -> httpx.Response:
        return self.response


def test_allows_a_permitted_page() -> None:
    decision = robots_decision(
        "https://example.test/catalog/film",
        "CineGraphExplorer",
        FakeClient(200, "User-agent: *\nAllow: /\n"),
    )
    assert decision.allowed is True


def test_denies_when_robots_cannot_be_retrieved() -> None:
    decision = robots_decision(
        "https://example.test/catalog/film",
        "CineGraphExplorer",
        FakeClient(503, ""),
    )
    assert decision.allowed is False


def test_denies_a_disallowed_path() -> None:
    decision = robots_decision(
        "https://example.test/private/film",
        "CineGraphExplorer",
        FakeClient(200, "User-agent: *\nDisallow: /private/\n"),
    )
    assert decision.allowed is False
