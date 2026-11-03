from app.services.external_catalog_identity_audit import match_summary_identity

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("catalog_audit", Path(__file__).resolve().parents[2] / "scripts/audit_external_catalog_overlap.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_identity_match_is_a_review_candidate_not_an_operational_fact():
    doc = {"document_id": "x", "identities": [{"wikidata_id": "Q42"}, {"wikidata_id": "Q42"}]}
    catalog = {"Q42": {"id": "film-1", "canonical_title": "Example", "review_status": "published"}}
    result = match_summary_identity(doc, catalog)
    assert result["match_status"] == "exact_qid_candidate"
    assert result["review_status"] == "review_required" and result["operational_eligible"] is False


def test_missing_or_ambiguous_identity_is_never_silently_resolved():
    assert match_summary_identity({"document_id": "x", "identities": [{}]}, {})["match_status"] == "missing_source_id"
    assert match_summary_identity({"document_id": "x", "identities": [{"wikidata_id": "Q1"}, {"wikidata_id": "Q2"}]}, {})["match_status"] == "ambiguous_or_invalid_source_id"
    assert match_summary_identity({"document_id": "x", "identities": [{"wikidata_id": "Q0"}]}, {})["match_status"] == "ambiguous_or_invalid_source_id"


def test_audit_rejects_nonlocal_and_overridden_host_addresses():
    audit.validate_local_dsn("host=127.0.0.1 port=5432 dbname=cinegraph")
    for dsn in ("host=localhost dbname=cinegraph", "host=127.0.0.1 dbname=cinegraph_test",
                "host=127.0.0.1 hostaddr=192.0.2.1 dbname=cinegraph"):
        with pytest.raises(ValueError, match="restricted"):
            audit.validate_local_dsn(dsn)
