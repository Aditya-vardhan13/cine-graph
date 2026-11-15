import pytest

from scripts.replay_writer_refresh_batch import select_qids


def test_only_story_present_candidates_are_selected_without_approving_them():
    report = {"schema": "cinegraph.writer-refresh-story-delta/v3", "review_status": "review_required",
              "entries": [{"qid": "Q1", "classification": "story_present_both"},
                          {"qid": "Q2", "classification": "possible_story_loss"},
                          {"qid": "Q3", "classification": "section_mix_requires_review"}]}
    assert select_qids(report) == ["Q1"]
    report["entries"].append({"qid": "Q1", "classification": "story_present_both"})
    with pytest.raises(ValueError, match="Duplicate"):
        select_qids(report)


def test_untrusted_report_cannot_be_used_as_selection():
    with pytest.raises(ValueError):
        select_qids({"schema": "other", "review_status": "review_required", "entries": []})
