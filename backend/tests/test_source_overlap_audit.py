import pytest

from app.services.source_overlap_audit import source_coverage, token_shingles


def test_coverage_is_directional_and_case_and_punctuation_insensitive():
    assert source_coverage("One two three four five.", "ONE, TWO THREE FOUR FIVE plus more")["candidate_coverage"] == 1
    assert source_coverage("one two three four five six", "one two three four five")["candidate_coverage"] == 0.5
    assert source_coverage("short text", "other") ["candidate_coverage"] is None
    with pytest.raises(ValueError):
        token_shingles("text", width=0)
