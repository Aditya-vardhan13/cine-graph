"""Pure selection contract checks; no model calls or substituted services."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from listwise_recovery_selector import validate_selection
from probe_inactive_recovery_pilot import focused_question


def test_selection_can_abstain_but_never_invent_or_duplicate_ids():
    assert validate_selection({"selected":[]},["1","2"])==[]
    assert validate_selection({"selected":["2","1"]},["1","2"])==["2","1"]
    for payload in ({"selected":["3"]},{"selected":["1","1"]},
                    {"selected":[1]},{"selected":"1"},{"selected":[],"claim":"invented"}):
        with pytest.raises(ValueError):
            validate_selection(payload,["1","2"])


def test_query_focus_preserves_question_and_does_not_supply_film_facts():
    question="Which decisions change the relationship?"
    assert focused_question(question).endswith(question)
    assert focused_question("What is this about?")=="What is this about?"
    assert focused_question("How did critics respond?").startswith("Attributed critical responses")
