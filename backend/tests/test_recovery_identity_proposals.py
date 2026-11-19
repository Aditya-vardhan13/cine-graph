import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("identity_proposals", Path(__file__).resolve().parents[2] / "scripts/prepare_recovery_identity_review.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_proposals_keep_ambiguous_matches_and_do_not_approve():
    rows = [{"target_rank": 1, "title": "Kung fu", "year_candidate": 2004}]
    searches = {1: [{"tconst": "tt1", "title": "Kung Fu Hustle", "year": 2004, "score": 0.95},
                    {"tconst": "tt2", "title": "Kung Fu Tea", "year": 2004, "score": 0.95}]}
    cross_ids = [{"imdb_id": "tt1", "wikidata_id": "Q1"}]
    result = module.propose(rows, searches, cross_ids)[0]
    assert not result["identity_approved"]
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["retained_cross_ids"] == cross_ids
    assert result["candidates"][1]["retained_cross_ids"] == []
