from dataclasses import replace

from app.services.research_metadata import MetadataAssertion, display_metadata


def fact(predicate, value, **changes):
    return MetadataAssertion("assertion-1", predicate, value, changes.get("qualifiers", {}),
                             changes.get("review_status", "resolved"), changes.get("rank", "normal"),
                             "https://www.wikidata.org/wiki/Q788822", "123")


def release(time, precision=11):
    return fact("release_event", {"type": "time", "time": time, "precision": precision,
                                 "calendar_model": "Q1985727"})


def test_earliest_recorded_release_does_not_confuse_rerelease_with_original():
    result = display_metadata([release("+2022-01-01T00:00:00Z"), release("+2005-11-18T00:00:00Z")], genre_labels={})
    assert result["release_date"] == "2005-11-18"
    assert result["release_year"] == 2005
    assert result["release_basis"] == "earliest_recorded_release"
    assert result["metadata_evidence"]["release_event"][0]["source_revision"] == "123"


def test_year_precision_does_not_invent_a_day():
    result = display_metadata([release("+2005-00-00T00:00:00Z", 9), release("+2005-11-18T00:00:00Z")], genre_labels={})
    assert result["release_year"] == 2005
    assert result["release_date"] is None


def test_unreviewed_deprecated_and_unsourced_values_are_not_displayed():
    value = release("+1999-01-01T00:00:00Z")
    result = display_metadata([replace(value, rank="deprecated"), replace(value, review_status="review_required"),
                               replace(value, source_url="")], genre_labels={})
    assert result["release_year"] is None
    assert result["metadata_evidence"]["release_event"] == []


def test_runtime_unit_conversion_and_conflicting_versions():
    minute = fact("runtime", {"amount": "+126", "unit": "Q7727"})
    second = fact("runtime", {"amount": "+7560", "unit": "Q11574"})
    assert display_metadata([minute, second], genre_labels={})["runtime_minutes"] == 126
    longer = fact("runtime", {"amount": "+140", "unit": "Q7727"})
    result = display_metadata([minute, longer], genre_labels={})
    assert result["runtime_minutes"] is None
    assert "runtime_requires_version_or_value_resolution" in result["metadata_issues"]
    qualified = replace(minute, qualifiers={"P518": [{"value": "extended_cut"}]})
    assert display_metadata([qualified], genre_labels={})["runtime_minutes"] is None


def test_genre_identifiers_are_preserved_without_inventing_labels_or_language():
    values = [fact("genre", {"wikidata_id": "Q1"}), fact("genre", {"wikidata_id": "Q2"})]
    result = display_metadata(values, genre_labels={"Q1": "drama film"})
    assert result["genres"] == ("drama film",)
    assert result["genre_ids"] == ("Q1", "Q2")
    assert result["language_code"] == "und"
    assert "some_genre_labels_unavailable" in result["metadata_issues"]
    assert display_metadata([fact("original_language", {"wikidata_id": "Q1860"})], genre_labels={})["language_code"] == "en"
