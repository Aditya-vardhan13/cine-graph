import hashlib

import pytest

from app.services.wikipedia_cast_candidates import extract_cast_candidates, is_cast_section


def _passage(locator: str, content: str, ordinal: int = 0) -> dict:
    return {
        "section_locator": locator,
        "section_title": locator.replace("/", " / "),
        "ordinal": ordinal,
        "content": content,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def test_cast_section_requires_a_cast_heading_not_a_casting_section():
    assert is_cast_section("voice-cast")
    assert is_cast_section("cast-and-characters")
    assert not is_cast_section("production/casting")
    assert not is_cast_section("legacy")


def test_extracts_explicit_actor_as_character_with_provenance_and_optional_qid_match():
    passage = _passage(
        "voice-cast",
        "Matthew Broderick as Simba, a young lion prince. Jeremy Irons as Scar, his uncle.",
    )
    result = extract_cast_candidates(
        film_qid="Q10",
        passages=[passage, _passage("production/casting", passage["content"], 1)],
        actors=[
            {"qid": "Q1", "label": "Matthew Broderick", "statement_locators": ["claims.P161[0]"]},
            {"qid": "Q2", "label": "Jeremy Irons", "statement_locators": ["claims.P161[1]"]},
        ],
        character_labels_by_actor={"Q1": [{"qid": "Q11", "label": "Simba"}]},
    )

    assert result["cast_passage_count"] == 1
    assert [row["character_name_in_source"] for row in result["candidates"]] == ["Simba", "Scar"]
    simba = result["candidates"][0]
    assert simba["actor_qid"] == "Q1"
    assert simba["matching_wikidata_character_qids"] == ["Q11"]
    assert simba["passage_sha256"] == passage["content_sha256"]
    assert simba["review_status"] == "review_required"
    assert result["ambiguities"] == []


def test_multiple_actor_as_phrases_in_one_sentence_do_not_bleed_roles():
    result = extract_cast_candidates(
        film_qid="Q10",
        passages=[_passage(
            "cast",
            "Actor One as Hermione Granger and Actor Two as Harry Potter, a wizard.",
        )],
        actors=[{"qid": "Q1", "label": "Actor One"}, {"qid": "Q2", "label": "Actor Two"}],
    )

    assert [(row["actor_qid"], row["character_name_in_source"]) for row in result["candidates"]] == [
        ("Q1", "Hermione Granger"), ("Q2", "Harry Potter")
    ]


def test_duplicate_english_actor_labels_are_quarantined_not_assigned():
    result = extract_cast_candidates(
        film_qid="Q10",
        passages=[_passage("cast", "Alex Lee as The Detective.")],
        actors=[{"qid": "Q1", "label": "Alex Lee"}, {"qid": "Q2", "label": "Alex Lee"}],
    )

    assert result["candidates"] == []
    assert result["ambiguities"][0]["candidate_actor_qids"] == ["Q1", "Q2"]
    assert result["ambiguities"][0]["reason"] == "ambiguous_actor_label"


def test_character_name_keeps_abbreviations_and_unmatched_names_stay_unresolved():
    result = extract_cast_candidates(
        film_qid="Q10",
        passages=[_passage("main-cast", "Dr. Actor as Mr. Hero.")],
        actors=[{"qid": "Q1", "label": "Dr. Actor"}],
    )
    assert result["candidates"][0]["character_name_in_source"] == "Mr. Hero"

    unmatched = extract_cast_candidates(
        film_qid="Q10",
        passages=[_passage("cast", "Unknown Actor as The Detective.")],
        actors=[{"qid": "Q1", "label": "Known Actor"}],
    )
    assert len(unmatched["candidates"]) == 1
    candidate = unmatched["candidates"][0]
    assert candidate["actor_label_in_source"] == "Unknown Actor"
    assert candidate["actor_qid"] is None
    assert candidate["identity_resolution"] == "unresolved_source_name"
    assert candidate["character_name_in_source"] == "The Detective"
    assert candidate["review_status"] == "review_required"


def test_group_cast_role_is_quarantined_instead_of_assigning_role_to_last_actor():
    result = extract_cast_candidates(
        film_qid="Q10",
        passages=[_passage(
            "voice-cast",
            "Whoopi Goldberg, Cheech Marin, and Jim Cummings as the three leaders of the group.",
        )],
        actors=[],
    )
    assert result["candidates"] == []
    assert result["ambiguities"][0]["reason"] == "group_role_not_individualized"


def test_multiline_actor_entry_is_not_combined_with_previous_text_and_role_stops_at_aside():
    result = extract_cast_candidates(
        film_qid="Q10",
        passages=[_passage(
            "voice-cast",
            "Earlier text refers to The Example Film.\n\nKnown Actor as Hero / The Mask (credited as 'Mask'), a brave lead.",
        )],
        actors=[{"qid": "Q1", "label": "Known Actor"}],
    )
    assert len(result["candidates"]) == 1
    row = result["candidates"][0]
    assert row["actor_qid"] == "Q1"
    assert row["character_name_in_source"] == "Hero / The Mask"
    assert result["ambiguities"] == []


def test_middle_initial_in_character_name_is_preserved():
    result = extract_cast_candidates(
        film_qid="Q10",
        passages=[_passage("voice-cast", "Jake Johnson as Peter B. Parker / Spider-Man: Miles' mentor.")],
        actors=[{"qid": "Q1", "label": "Jake Johnson"}],
    )
    assert result["candidates"][0]["character_name_in_source"] == "Peter B. Parker / Spider-Man"


def test_quoted_actor_nickname_and_suffix_are_retained_as_source_name():
    result = extract_cast_candidates(
        film_qid="Q10",
        passages=[_passage("voice-cast", 'Marvin "Krondon" Jones III as Tombstone, Kingpin’s bodyguard.')],
        actors=[],
    )
    assert result["candidates"][0]["actor_label_in_source"] == 'Marvin "Krondon" Jones III'
    assert result["candidates"][0]["character_name_in_source"] == "Tombstone"
    assert result["candidates"][0]["actor_qid"] is None


def test_known_actor_in_group_role_is_also_quarantined():
    result = extract_cast_candidates(
        film_qid="Q10",
        passages=[_passage("cast", "Other Actor, Another Actor, and Known Actor as the three leaders.")],
        actors=[{"qid": "Q1", "label": "Known Actor"}],
    )
    assert result["candidates"] == []
    assert result["ambiguities"][0]["candidate_actor_qids"] == ["Q1"]
    assert result["ambiguities"][0]["reason"] == "group_role_not_individualized"


def test_tampered_passage_content_is_rejected():
    passage = _passage("cast", "Actor One as Character One.")
    passage["content"] = "Actor One as Character Two."
    with pytest.raises(ValueError, match="hash"):
        extract_cast_candidates(
            film_qid="Q10", passages=[passage], actors=[{"qid": "Q1", "label": "Actor One"}]
        )
