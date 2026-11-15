import pytest

from scripts.replay_held_writer_refresh import revision_action


def test_only_newer_revisions_are_candidates_for_replay():
    assert revision_action("100", "101") == "newer"
    assert revision_action("100", "100") == "same"
    assert revision_action("100", "99") == "older"
    with pytest.raises(ValueError):
        revision_action("invalid", "100")
