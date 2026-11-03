"""Pure comparison checks; no corpus or network is touched."""
from dataclasses import dataclass
import importlib.util
from pathlib import Path

import pytest


path = Path(__file__).resolve().parents[2] / "scripts/audit_wikipedia_parser_delta.py"
spec = importlib.util.spec_from_file_location("audit_wikipedia_parser_delta", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@dataclass
class Passage:
    section_locator: str
    ordinal: int
    content: str


def test_changed_and_shifted_passages_are_reported_separately():
    old = [Passage("plot", 0, "old"), Passage("plot", 1, "same")]
    new = [Passage("plot", 0, "new"), Passage("plot", 2, "same")]
    assert module.compare_passages(old, new) == {
        "old_passages": 2, "new_passages": 2, "changed_shared_keys": 1,
        "old_only_keys": 1, "new_only_keys": 1, "changed_locators": ["plot"],
        "sections_with_possible_v2_text_loss": ["plot"],
    }


def test_duplicate_keys_fail_instead_of_silently_dropping_content():
    with pytest.raises(ValueError, match="Duplicate"):
        module.compare_passages([Passage("plot", 0, "a"), Passage("plot", 0, "b")], [])


def test_rechunking_and_insertions_do_not_look_like_deleted_text():
    old = [Passage("plot", 0, "A person"), Passage("plot", 1, "leaves town.")]
    new = [Passage("plot", 0, "A young person leaves"), Passage("plot", 1, "town.")]
    assert module.compare_passages(old, new)["sections_with_possible_v2_text_loss"] == []


def test_deletions_in_an_entire_missing_section_are_flagged():
    old = [Passage("plot", 0, "A person leaves"), Passage("cast", 0, "Someone")]
    new = [Passage("plot", 0, "A person")]
    assert module.compare_passages(old, new)["sections_with_possible_v2_text_loss"] == ["cast", "plot"]
