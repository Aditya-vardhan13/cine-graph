import pytest

from app.services.external_narrative_preparation import (
    category_set, claim_arms, claim_pair_status, narrative_case, passage_windows, srt_text,
)


def test_category_policy_preserves_set_without_empty_tags():
    assert category_set("Temporal, Event/Entity , Temporal,") == ["Event/Entity", "Temporal"]


def test_invalid_contrastive_pairs_are_not_scored_and_arm_positions_vary():
    assert claim_pair_status({"true_claim": "Same.", "false_claim": " Same. "}) == "identical_claims"
    assert claim_pair_status({"true_claim": "", "false_claim": "Different."}) == "empty_claim"
    row = {"true_claim": "One.", "false_claim": "Two."}
    arms = [claim_arms(str(i), row) for i in range(20)]
    assert {a[0][2] for a in arms} == {True, False}
    assert all({(text, truth) for _, text, truth in a} == {("One.", True), ("Two.", False)} for a in arms)


def test_model_projection_drops_labels_and_comments():
    row = {"anchor_text": "An anchor.", "text_a": "A story.", "text_b": "Another story.",
           "text_a_is_closer": True, "human_labels": [True, True], "additional_comment": "SECRET"}
    prompt, gold = narrative_case(row, split="dev", case_id="D")
    assert set(prompt) == {"case_id", "dataset", "official_split", "task", "stories"}
    assert "SECRET" not in str(prompt) and "human_labels" not in prompt
    assert gold["a_is_closer"] is True
    with pytest.raises(ValueError, match="boolean"):
        narrative_case({**row, "text_a_is_closer": "yes"}, split="dev", case_id="D")


def test_retained_mf2_subtitle_excerpt_preserves_dialogue_offsets():
    # MF2, CC BY 4.0 release; data/transcripts/1.srt, cues 1-2.
    # https://github.com/deep-spin/MF2-bench-how-well-vlms-understand-movies/
    # blob/e00ff56479c88fcc9947d4975c8deba93e42e922/data/transcripts/1.srt
    raw = "1\n00:06:01,195 --> 00:06:02,070\nWhat are you doing here?\n\n2\n00:06:05,366 --> 00:06:07,326\nGet out! This is my house!\n"
    text, cues = srt_text(raw)
    assert len(cues) == 2 and cues[0]["start_ms"] == 361195
    assert all(raw[c["raw_start"]:c["raw_end"]] == text[c["content_start"]:c["content_end"]] for c in cues)
    assert "-->" not in text


def test_nonstandard_source_layout_does_not_invent_cues_or_drop_text():
    raw = "-1\r\n00:00:02,42 --> 00:00:08,35\r\nA line.\r\n\r\nUnnumbered continuation.\r\n\r\n1\r\n00:00:09,230 --> 00:00:10,000\r\nLast line."
    text, cues = srt_text(raw)
    assert cues[0]["start_ms"] == 2420 and cues[0]["cue_number"] == -1
    assert cues[1]["timestamp_status"] == "untimed-source-block"
    assert cues[1]["start_ms"] is None and "Unnumbered continuation." in text
    assert all(raw[c["raw_start"]:c["raw_end"]] == text[c["content_start"]:c["content_end"]] for c in cues)


def test_bad_time_headers_fail_and_passages_are_exact_substrings():
    with pytest.raises(ValueError):
        srt_text("1\n00:00:02,000 --> 00:00:01,000\nBackwards.")
    with pytest.raises(ValueError):
        srt_text("No timed cues at all.")
    value = "One two\nthree four five six seven."
    spans = passage_windows(value, words=4, overlap=1)
    assert all(value[s["start"]:s["end"]] == s["content"] for s in spans)
    assert spans[-1]["end"] == len(value)
