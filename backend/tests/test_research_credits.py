"""Source-credit extraction policy; no mocks or network."""
from app.services.research_credits import credit_from_statement


def test_imdb_cast_character_stays_attached_to_source() -> None:
    credit = credit_from_statement(
        "cast", {"name": "Heath Ledger", "characters": ["Joker"], "position": 2},
        "https://www.imdb.com/title/tt0468569/",
    )
    assert credit is not None
    assert (credit.name, credit.role, credit.character_name, credit.position) == ("Heath Ledger", "cast", "Joker", 2)
    assert credit.source_url == "https://www.imdb.com/title/tt0468569/"


def test_tmdb_character_is_not_invented_when_absent() -> None:
    credit = credit_from_statement("cast", {"name": "Someone", "character": ""}, "https://www.themoviedb.org/movie/1")
    assert credit is not None and credit.character_name is None


def test_unattributed_or_non_credit_statement_is_not_displayed() -> None:
    assert credit_from_statement("cast", {"name": "Someone"}, "local") is None
    assert credit_from_statement("genre", {"name": "Someone"}, "https://example.org") is None
