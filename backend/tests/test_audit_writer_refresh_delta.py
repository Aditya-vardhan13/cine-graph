from scripts.audit_writer_refresh_delta import classify, compare_versions, measurements


def test_story_aliases_and_nested_sections_are_counted():
    assert measurements([("plot", "abc"), ("synopsis/part-one", "de"),
                         ("plot-summary", "f"), ("production", "ignored")]) == {
                             "passages": 3, "characters": 6}


def test_delta_flags_missing_and_potential_loss_without_approving_quality():
    assert classify({"characters": 0}, {"characters": 3}) == "story_newly_available"
    assert classify({"characters": 10}, {"characters": 0}) == "new_story_missing"
    assert classify({"characters": 0}, {"characters": 0}) == "story_missing_both"
    assert classify({"characters": 10}, {"characters": 6}) == "possible_story_loss"
    assert classify({"characters": 10}, {"characters": 7}) == "story_present_both"


def test_prior_extraction_versions_are_not_silently_combined():
    classification, versions = compare_versions({"v1": [("plot", "abc")], "v2": [("plot", "abcdef")]},
                                                 {"passages": 1, "characters": 4})
    assert classification == "prior_extraction_ambiguous"
    assert versions["v1"]["characters"] == 3
    assert versions["v2"]["characters"] == 6
