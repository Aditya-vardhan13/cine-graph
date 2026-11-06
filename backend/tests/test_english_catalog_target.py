import json

import pytest

from app.services.english_catalog_target import (
    build_english_catalog_target,
    validate_english_catalog_target,
)


def test_target_preserves_rank_duplicates_and_only_title_year_fields():
    source = (
        b"Poster_Link,Series_Title,Released_Year,Overview,IMDB_Rating\n"
        b"poster-a,Film A,2001,plot must not be copied,9.9\n"
        b"poster-b,Film A,2001,also not copied,1.0\n"
        b"poster-c,Film C,2003,also not copied,2.0\n"
    )
    manifest = build_english_catalog_target(source, expected_count=2)
    assert manifest["candidate_count"] == 2
    assert manifest["input_row_count"] == 3
    assert manifest["out_of_scope_rows_after_selection"] == [
        {"input_row": 3, "title": "Film C", "release_year_candidate": 2003},
    ]
    assert manifest["catalog_identity_resolved"] is False
    assert manifest["official_or_current_ranking_claim"] is False
    assert manifest["candidates"] == [
        {"selection_rank": 1, "input_row": 1, "title": "Film A",
         "release_year_candidate": 2001, "catalog_identity_status": "unresolved"},
        {"selection_rank": 2, "input_row": 2, "title": "Film A",
         "release_year_candidate": 2001, "catalog_identity_status": "duplicate_candidate_review",
         "duplicate_candidate_of_rank": 1},
    ]
    assert "plot must not be copied" not in json.dumps(manifest)
    assert "9.9" not in json.dumps(manifest)


def test_target_manifest_is_bound_to_exact_input_bytes():
    source = b"Series_Title,Released_Year\nFilm,2001\n"
    target = build_english_catalog_target(source, expected_count=1)
    assert validate_english_catalog_target(target, source, expected_count=1)["valid"]
    with pytest.raises(ValueError, match="fingerprint"):
        validate_english_catalog_target(target, source + b"\n", expected_count=1)


@pytest.mark.parametrize("source, message", [
    (b"Series_Title,Released_Year\nFilm,2001\n", "at least 2"),
    (b"Name,Year\nFilm,2001\n", "missing required"),
    (b"Series_Title,Released_Year\nFilm,202\nFilm B,2002\n", "invalid four-digit"),
    (b"Series_Title,Released_Year\nSeries_Title,Released_Year\nFilm B,2002\n", "invalid title"),
])
def test_target_rejects_malformed_or_wrong_sized_candidate_lists(source, message):
    with pytest.raises(ValueError, match=message):
        build_english_catalog_target(source, expected_count=2)
