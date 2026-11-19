import json
from collections import Counter
from pathlib import Path


def test_recovery_questions_are_complete_disjoint_by_pair_and_not_gold():
    packet = json.loads((Path(__file__).parent / "fixtures/recovery-question-design-v1.json").read_text())
    assert packet["independent_gold"] is False
    assert packet["popularity_verified"] is False
    pairs = packet["pairs"]
    assert len(pairs) == 10
    assert len({p["id"] for p in pairs}) == 10
    assert len({tuple(sorted(p["films"])) for p in pairs}) == 10
    assert len({f for p in pairs for f in p["films"]}) == 10
    assert all(len(p["questions"]) == 5 and len(p["films"]) == 2 for p in pairs)
    assert len({q for p in pairs for q in p["questions"]}) == 50
    assert Counter(p["split"] for p in pairs) == {"development": 6, "question_holdout": 4}
    assert all(p["discovery_urls"] for p in pairs)
