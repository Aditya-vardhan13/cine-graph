from dataclasses import replace

from app.schemas import ResearchReleaseEventOut, ResearchRuntimeOptionOut
from app.services.research_metadata import MetadataAssertion, display_metadata


def fact(predicate, value, **changes):
    return MetadataAssertion("assertion-1", predicate, value, changes.get("qualifiers", {}),
                             changes.get("review_status", "resolved"), changes.get("rank", "normal"),
                             "https://www.wikidata.org/wiki/Q788822", "123",
                             changes.get("source_name"), changes.get("source_rights_status"),
                             changes.get("source_license"))


def release(time, precision=11):
    return fact("release_event", {"type": "time", "time": time, "precision": precision,
                                 "calendar_model": "Q1985727"})


def test_earliest_recorded_release_does_not_confuse_rerelease_with_original():
    result = display_metadata([release("+2022-01-01T00:00:00Z"), release("+2005-11-18T00:00:00Z")], genre_labels={})
    assert result["release_date"] == "2005-11-18"
    assert result["release_year"] == 2005
    assert result["release_basis"] == "earliest_recorded_release"
    assert result["metadata_evidence"]["release_event"][0]["source_revision"] == "123"


def test_all_release_events_keep_their_place_and_source_context():
    first = release("+2008-07-18T00:00:00Z")
    later = replace(
        release("+2022-10-06T00:00:00Z"),
        assertion_id="later-release",
        qualifiers={"P291": [{"datavalue": {"value": {"id": "Q851"}}}]},
    )
    result = display_metadata([later, first], genre_labels={})
    assert result["release_date"] == "2008-07-18"
    assert [event["date"] for event in result["release_events"]] == [
        "2008-07-18", "2022-10-06",
    ]
    assert result["release_events"][1]["place_ids"] == ["Q851"]
    assert result["release_events"][1]["assertion_id"] == "later-release"
    assert result["release_events"][0]["precision"] == 11


def test_year_precision_does_not_invent_a_day():
    result = display_metadata([release("+2005-00-00T00:00:00Z", 9), release("+2005-11-18T00:00:00Z")], genre_labels={})
    assert result["release_year"] == 2005
    assert result["release_date"] is None
    assert [event["precision"] for event in result["release_events"]] == [9, 11]


def test_unsupported_subday_precision_is_not_truncated_to_a_date():
    result = display_metadata([release("+2005-11-18T00:00:00Z", 12)], genre_labels={})
    assert result["release_events"] == ()
    assert "release_value_not_displayable" in result["metadata_issues"]


def test_release_event_response_preserves_year_precision_and_provenance():
    event = display_metadata([release("+2005-00-00T00:00:00Z", 9)], genre_labels={})["release_events"][0]
    response = ResearchReleaseEventOut(**event)
    assert response.year == 2005
    assert response.date is None
    assert response.precision == 9
    assert response.source_revision == "123"


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


def test_runtime_options_preserve_source_scopes_and_bounds():
    theatrical = replace(
        fact("runtime", {"type": "quantity", "amount": "+148", "unit": "Q7727"},
             source_name="Wikidata", source_rights_status="open", source_license="CC0 1.0"),
        assertion_id="theatrical-runtime",
        qualifiers={"P518": [{"datavalue": {"value": {"id": "Q26225765"}}}]},
    )
    alternate = replace(
        fact("runtime", {"type": "quantity", "amount": "+152", "unit": "Q7727"},
             source_name="Wikidata", source_rights_status="open", source_license="CC0 1.0"),
        assertion_id="alternate-runtime",
    )
    approximate = replace(
        fact("runtime", {"type": "quantity", "amount": "+118", "unit": "Q7727",
                          "lower_bound": "+117", "upper_bound": "+119"}),
        assertion_id="approximate-runtime",
    )

    result = display_metadata([alternate, theatrical, approximate], genre_labels={})

    assert result["runtime_minutes"] is None
    assert [item["minutes"] for item in result["runtime_options"]] == [118, 148, 152]
    assert result["runtime_options"][0]["lower_bound_minutes"] == 117
    assert result["runtime_options"][0]["upper_bound_minutes"] == 119
    assert result["runtime_options"][1]["scope"] == [
        {"property_id": "P518", "entity_ids": ["Q26225765"]},
    ]
    response = ResearchRuntimeOptionOut(**result["runtime_options"][1])
    assert response.source_license == "CC0 1.0"
    assert response.source_rights_status == "open"


def test_genre_identifiers_are_preserved_without_inventing_labels_or_language():
    values = [fact("genre", {"wikidata_id": "Q1"}), fact("genre", {"wikidata_id": "Q2"})]
    result = display_metadata(values, genre_labels={"Q1": "drama film"})
    assert result["genres"] == ("drama film",)
    assert result["genre_ids"] == ("Q1", "Q2")
    assert result["language_code"] == "und"
    assert "some_genre_labels_unavailable" in result["metadata_issues"]
    assert display_metadata([fact("original_language", {"wikidata_id": "Q1860"})], genre_labels={})["language_code"] == "en"
