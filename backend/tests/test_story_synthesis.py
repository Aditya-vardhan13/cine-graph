"""Pure validation tests; no network, model, or mocked services."""
import json

import pytest

from app.services.story_synthesis import CitedSource, _validate_model_brief


SOURCES = {
    ref: CitedSource(ref, f"chunk-{ref}", "Plot", f"https://example.org/{ref}", "rev-1", "CC BY-SA 4.0", "Retained fixture passage.")
    for ref in ("A1", "A2", "B1", "B2")
}


def brief(*, first_refs=("A1",), second_refs=("B1",), contrast_refs=("A1", "B1")) -> str:
    return json.dumps({
        "first": {"text": "The first film makes the protagonist choose publicly between competing obligations.", "refs": first_refs},
        "second": {"text": "The second film makes that same public choice cost a private relationship.", "refs": second_refs},
        "contrast": {"text": "The first risks public trust, while the second risks an intimate relationship.", "refs": contrast_refs},
        "writing_move": "Put your protagonist before both constituencies and let one choice damage the other relationship.",
    })


def test_model_brief_maps_only_provided_source_references() -> None:
    result = _validate_model_brief(brief(), SOURCES)
    assert result.first.sources[0].chunk_id == "chunk-A1"
    assert result.second.sources[0].source_url == "https://example.org/B1"
    assert [source.ref for source in result.contrast.sources] == ["A1", "B1"]


@pytest.mark.parametrize("payload", [
    brief(first_refs=("B1",)),
    brief(second_refs=("B3",)),
    brief(contrast_refs=("A1",)),
    brief(contrast_refs=("B1",)),
])
def test_model_brief_rejects_invented_or_wrong_film_citations(payload: str) -> None:
    with pytest.raises(ValueError):
        _validate_model_brief(payload, SOURCES)


def test_model_brief_rejects_source_heading_as_a_film_reading() -> None:
    payload = json.loads(brief())
    payload["first"]["text"] = "Her · Plot"
    with pytest.raises(ValueError, match="uncited or invalid reading"):
        _validate_model_brief(json.dumps(payload), SOURCES)


def test_model_brief_rejects_repeated_question_as_writing_move() -> None:
    question = "How do these films turn loneliness into a character choice?"
    payload = json.loads(brief())
    payload["writing_move"] = question
    with pytest.raises(ValueError, match="no creative prompt"):
        _validate_model_brief(json.dumps(payload), SOURCES, question)
