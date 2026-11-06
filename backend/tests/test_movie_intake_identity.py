import pytest

from app.services.movie_intake_identity import identity_issue
from app.services.wikidata import WikidataQueryRouteUnavailable, sparql_query_runner
from app.services.wikidata_imdb_resolver import WikidataImdbDiscoveryUnavailable, acquire
from app.services.indian_film_selection import acquire_candidates
from app.admin_intake import intake_status_label, local_operator_email_allowed


def _entity() -> dict:
    return {
        "id": "Q123",
        "labels": {"en": {"value": "Example Film"}},
        "aliases": {},
        "claims": {
            "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}],
            "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+2000-01-01T00:00:00Z"}}}}],
            "P345": [{"mainsnak": {"datavalue": {"value": "tt1234567"}}}],
        },
    }


def test_intake_identity_requires_article_qid_film_year_title_and_imdb_agreement() -> None:
    assert identity_issue(article_qid="Q123", entity=_entity(), title="Example Film",
                          year=2000, imdb_id="tt1234567") is None
    assert identity_issue(article_qid="Q124", entity=_entity(), title="Example Film",
                          year=2000, imdb_id="tt1234567") == (
        "Wikipedia article QID does not match the retained Wikidata entity"
    )
    assert identity_issue(article_qid="Q123", entity=_entity(), title="Other Film",
                          year=2000, imdb_id="tt1234567") is not None
    assert identity_issue(article_qid="Q123", entity=_entity(), title="Example Film",
                          year=2001, imdb_id="tt1234567") is not None
    assert identity_issue(article_qid="Q123", entity=_entity(), title="Example Film",
                          year=2000, imdb_id="tt7654321") is not None


def test_wikidata_query_service_runner_fails_closed_without_network() -> None:
    with pytest.raises(WikidataQueryRouteUnavailable, match="/sparql is disabled"):
        sparql_query_runner()


def test_imdb_qid_resolver_never_queries_disallowed_route(tmp_path) -> None:
    with pytest.raises(WikidataImdbDiscoveryUnavailable, match="/sparql is disabled"):
        acquire("SELECT * WHERE {}", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_indian_selection_never_fetches_when_no_retained_cache_exists(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="/sparql candidate discovery is disabled"):
        acquire_candidates("te", tmp_path, limit=5)
    assert list(tmp_path.iterdir()) == []


def test_email_operator_gate_is_local_only_and_case_insensitive() -> None:
    assert local_operator_email_allowed(
        "AdityaVK1310@gmail.com", expected="adityavk1310@gmail.com",
        environment="development",
    )
    assert not local_operator_email_allowed(
        "adityavk1310@gmail.com", expected="adityavk1310@gmail.com",
        environment="production",
    )
    assert not local_operator_email_allowed(
        "someone@example.com", expected="adityavk1310@gmail.com",
        environment="development",
    )


def test_intake_status_labels_never_call_source_capture_indexing_readiness() -> None:
    assert intake_status_label("captured") == "Capture complete"
    assert intake_status_label("captured_with_gaps") == "Captured with gaps"
    assert intake_status_label("ready") == "Captured · legacy status"
