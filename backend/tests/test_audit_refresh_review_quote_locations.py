import pytest

from scripts.audit_refresh_review_quote_locations import locations, whitespace_locations


def test_locations_keep_passage_offsets_and_report_ambiguity():
    assert locations("abc", [("one", "xabc yabc"), ("two", "abc")]) == [
        {"passage_id": "one", "start": 1, "end": 4},
        {"passage_id": "one", "start": 6, "end": 9},
        {"passage_id": "two", "start": 0, "end": 3},
    ]
    assert locations("missing", [("one", "abc")]) == []
    with pytest.raises(ValueError):
        locations("", [("one", "abc")])


def test_whitespace_match_preserves_offsets_without_ignoring_punctuation():
    assert whitespace_locations("one two", [("p", "x one\n\ntwo z")]) == [
        {"passage_id": "p", "start": 2, "end": 10}
    ]
    assert whitespace_locations("one, two", [("p", "one two")]) == []
    with pytest.raises(ValueError):
        whitespace_locations("  ", [("p", "abc")])
