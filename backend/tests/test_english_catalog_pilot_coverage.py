import hashlib
import json

import pytest

from scripts.render_english_catalog_pilot_coverage import build_rows, render_markdown


def sample_reports():
    pilot = {"film_count": 100, "films": []}
    readiness = {"database_read_only": True, "films": []}
    for rank in range(1, 101):
        film_id = f"film-{rank}"
        qid = f"Q{rank}"
        pilot["films"].append({
            "selection_rank": rank,
            "input_rank": rank + 10,
            "input_title": f"Film {rank}",
            "input_year": 2000 + rank,
            "catalog_match": "exact_title_year",
            "catalog_film_id": film_id,
            "catalog_title": f"Film {rank}",
            "wikidata_id": qid,
            "catalog_language": "en",
        })
        readiness["films"].append({
            "film_id": film_id,
            "wikidata_id": qid,
            "title": f"Film {rank}",
            "language": "en",
            "identity_status": "linked",
            "release_years_from_resolved_events": [str(2000 + rank)],
            "runtime_minutes": None,
            "resolved_assertions": {"director": 1, "writer": 2, "cast": 6, "character": 1},
            "narrative_categories": ["plot", "production"],
            "source_versions": ["fixture-v1"],
            "narrative_use_coverage": {
                "total": 2, "with_license_and_attribution": 2,
                "with_decision": 1, "approved": 0, "denied": 0,
                "review_required": 1, "eligible": 0,
            },
            "embedding_vectors": 3,
            "semantically_eligible_embedding_vectors": 0,
            "gaps": ["runtime_minutes", "semantically_eligible_indexed"],
        })
    return pilot, readiness


def sample_cast_review(pilot):
    report = {
        "schema": "cinegraph.wikipedia-cast-candidate-coverage/v1",
        "pilot_manifest_sha256": hashlib.sha256(json.dumps(pilot).encode()).hexdigest(),
        "summary": {
            "films": 100,
            "candidate_rows": 800,
            "same_film_identity_candidates": 500,
            "identity_only_candidates_with_review_drafts": 100,
            "review_only_source_statement_drafts": 600,
            "identity_only_suggestions": 100,
            "unresolved_source_names": 200,
            "character_label_matches_only": 300,
            "quarantined_spans": 100,
            "all_candidates_review_required": True,
            "actor_character_credits_verified": False,
            "operational_assertions_written": False,
        },
        "films": [{
            "selection_rank": rank,
            "title": f"Film {rank}",
            "film_qid": f"Q{rank}",
            "year": 2000 + rank,
            "candidate_count": 8,
            "same_film_identity_candidates": 5,
            "identity_only_suggestions": 1,
            "unresolved_source_names": 2,
            "quarantined_spans": 1,
            "source_statement_drafts": 6,
            "character_label_matches_only": 3,
            "quarantine_reasons": {"ambiguous_span": 1},
        } for rank in range(1, 101)],
    }
    return report


def build_rows_with_cast(pilot, readiness, cast_review):
    return build_rows(
        pilot, readiness, cast_review,
        pilot_sha256=hashlib.sha256(json.dumps(pilot).encode()).hexdigest(),
    )


def test_english_coverage_sheet_exposes_per_film_gaps_and_rights_state():
    pilot, readiness = sample_reports()
    rows = build_rows(pilot, readiness)
    assert len(rows) == 100
    assert rows[0]["resolved_assertions"] == {"director": 1, "writer": 2, "cast": 6, "character": 1}
    assert rows[0]["snapshots"]["eligible"] == 0
    assert rows[0]["vectors"] == {"stored": 3, "eligible": 0}
    report = render_markdown(rows, pilot_sha256="pilot-hash", readiness_sha256="readiness-hash")
    assert "all selected from unique exact title/year catalog matches classified `en`" in report
    assert "2/2/0/0" in report
    assert "runtime_minutes, semantically_eligible_indexed" in report
    assert "Q1" in report


@pytest.mark.parametrize("mutation, message", [
    ("wrong_manifest_language", "not English-classified"),
    ("wrong_readiness_language", "Readiness language mismatch"),
    ("wrong_qid", "Wikidata identity mismatch"),
    ("duplicate_id", "must be unique strings"),
])
def test_english_coverage_sheet_rejects_scope_or_identity_mismatch(mutation, message):
    pilot, readiness = sample_reports()
    if mutation == "wrong_manifest_language":
        pilot["films"][0]["catalog_language"] = "und"
    elif mutation == "wrong_readiness_language":
        readiness["films"][0]["language"] = "und"
    elif mutation == "wrong_qid":
        readiness["films"][0]["wikidata_id"] = "Q-wrong"
    else:
        pilot["films"][1]["catalog_film_id"] = pilot["films"][0]["catalog_film_id"]
    with pytest.raises(ValueError, match=message):
        build_rows(pilot, readiness)


def test_english_coverage_sheet_requires_read_only_snapshot():
    pilot, readiness = sample_reports()
    readiness["database_read_only"] = False
    with pytest.raises(ValueError, match="database_read_only"):
        build_rows(pilot, readiness)


def test_english_coverage_sheet_joins_cast_candidates_without_calling_them_verified():
    pilot, readiness = sample_reports()
    rows = build_rows_with_cast(pilot, readiness, sample_cast_review(pilot))

    assert len(rows) == 100
    assert rows[0]["cast_review"] == {
        "candidate_rows": 8,
        "same_film_identity_candidates": 5,
        "identity_only_suggestions": 1,
        "unresolved_source_names": 2,
        "quarantined_spans": 1,
        "review_only_drafts": 6,
        "character_label_matches_only": 3,
        "identity_supplemented_candidates": 0,
        "quarantine_reasons": {"ambiguous_span": 1},
        "credit_status": "candidate_only_not_verified",
    }
    report = render_markdown(
        rows, pilot_sha256="pilot-hash", readiness_sha256="readiness-hash",
        cast_review_sha256="cast-hash",
    )
    assert "800 candidate rows" in report
    assert "100 identity-only suggestions" in report
    assert "600 review-only drafts" in report
    assert "not approved or verified actor–character credits" in report
    assert "Cast rows / review-only drafts / identity-only / unresolved / quarantined" in report
    assert "6 / 1 / 2 / 1" in report
    assert "Cast-candidate coverage SHA-256: `cast-hash`" in report


def test_english_coverage_sheet_reports_curated_identity_supplement_as_unverified():
    pilot, readiness = sample_reports()
    cast_review = sample_cast_review(pilot)
    cast_review["schema"] = "cinegraph.wikipedia-cast-candidate-coverage/v2"
    cast_review["summary"]["identity_supplemented_candidates"] = 9
    for film in cast_review["films"]:
        film["identity_supplemented_candidates"] = 0
    cast_review["films"][0]["identity_supplemented_candidates"] = 9
    cast_review["films"][0]["identity_only_suggestions"] = 10
    cast_review["summary"]["identity_only_suggestions"] = 109
    cast_review["summary"]["identity_only_candidates_with_review_drafts"] = 109

    rows = build_rows_with_cast(pilot, readiness, cast_review)
    assert rows[0]["cast_review"]["identity_supplemented_candidates"] == 9
    rendered = render_markdown(
        rows, pilot_sha256="pilot-hash", readiness_sha256="readiness-hash",
        cast_review_sha256="cast-hash",
    )
    assert "Curated Wikidata identity supplement: **9**" in rendered
    assert "still require human review" in rendered


def test_english_coverage_sheet_rejects_inconsistent_identity_supplement_totals():
    pilot, readiness = sample_reports()
    cast_review = sample_cast_review(pilot)
    cast_review["schema"] = "cinegraph.wikipedia-cast-candidate-coverage/v2"
    cast_review["summary"]["identity_supplemented_candidates"] = 1
    for film in cast_review["films"]:
        film["identity_supplemented_candidates"] = 0
    with pytest.raises(ValueError, match="supplemental identity summary"):
        build_rows_with_cast(pilot, readiness, cast_review)


@pytest.mark.parametrize("mutation, message", [
    ("wrong_qid", "Wikidata identity mismatch at pilot rank 1"),
    ("wrong_year", "release-year mismatch at pilot rank 1"),
    ("duplicate_rank", "repeats selection rank 1"),
    ("wrong_pilot_hash", "not bound to the exact English pilot manifest"),
    ("verified_claim", "full, review-only pilot audit"),
    ("bad_quarantine_total", "quarantine totals disagree at pilot rank 1"),
    ("invalid_count", "count candidate_count is invalid at pilot rank 1"),
])
def test_english_coverage_sheet_rejects_misaligned_cast_candidate_report(mutation, message):
    pilot, readiness = sample_reports()
    cast_review = sample_cast_review(pilot)
    if mutation == "wrong_qid":
        cast_review["films"][0]["film_qid"] = "Q999"
    elif mutation == "wrong_year":
        cast_review["films"][0]["year"] += 1
    elif mutation == "duplicate_rank":
        cast_review["films"][1]["selection_rank"] = 1
    elif mutation == "wrong_pilot_hash":
        cast_review["pilot_manifest_sha256"] = "f" * 64
    elif mutation == "verified_claim":
        cast_review["summary"]["actor_character_credits_verified"] = True
    elif mutation == "bad_quarantine_total":
        cast_review["films"][0]["quarantine_reasons"] = {"ambiguous_span": 2}
    else:
        cast_review["films"][0]["candidate_count"] = -1
    with pytest.raises(ValueError, match=message):
        build_rows_with_cast(pilot, readiness, cast_review)
