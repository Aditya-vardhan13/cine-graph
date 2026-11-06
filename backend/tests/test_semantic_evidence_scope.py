from sqlalchemy.dialects import postgresql

from app.services.semantic_evidence_scope import semantically_approved_chunk_ids


def test_retrieval_scope_rechecks_snapshot_license_attribution_and_approval_urls():
    compiled = semantically_approved_chunk_ids().compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "source_snapshots.license IN" in sql
    assert "source_snapshots.attribution_url" in sql
    assert "lower(source_snapshots.attribution_url) ~" in sql
    assert "lower(narrative_use_decisions_1.decision_basis_url) ~" in sql
    assert any("@]+" in str(value) for value in compiled.params.values())
    assert "narrative_use_decisions_1.decision =" in sql
