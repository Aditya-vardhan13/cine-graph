from scripts.audit_writer_identity_exceptions import classify_exception


def classify(**updates):
    values = {"url_title": "Title (film)", "captured_title": "Title", "sitelink_title": "Title",
              "expected_page_id": "enwiki:123", "captured_page_id": 123,
              "expected_revision": "456", "captured_revision": 456}
    return classify_exception(**(values | updates))


def test_title_difference_is_only_a_review_observation():
    assert classify() == "retained_title_matches_sitelink_url_differs"
    assert classify(url_title="Title") == "retained_title_and_sitelink_match"


def test_missing_sitelink_or_wrong_source_never_classifies_as_title_change():
    assert classify(sitelink_title=None) == "wikidata_sitelink_missing"
    assert classify(sitelink_title="Another title") == "wikidata_sitelink_conflicts_with_retained_title"
    assert classify(captured_page_id=999) == "wikipedia_identity_or_revision_conflict"
    assert classify(captured_revision=999) == "wikipedia_identity_or_revision_conflict"
    assert classify(captured_title=None) == "incomplete_wikipedia_observation"
