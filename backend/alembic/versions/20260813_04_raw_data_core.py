"""Add immutable raw-source snapshots and normalized claim storage."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_04"
down_revision: Union[str, None] = "20260813_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid() -> sa.Uuid:
    return sa.Uuid()


def upgrade() -> None:
    op.create_table(
        "source_access_policies",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("access_mode", sa.String(length=20), nullable=False),
        sa.Column("policy_url", sa.String(length=500), nullable=False),
        sa.Column("policy_revision", sa.String(length=150)),
        sa.Column("robots_url", sa.String(length=500)),
        sa.Column("robots_decision", sa.String(length=40)),
        sa.Column("allowed_paths", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("required_user_agent", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("max_requests_per_minute", sa.Integer()),
        sa.Column("max_concurrency", sa.Integer()),
        sa.Column("decision", sa.String(length=30), nullable=False, server_default="review_required"),
        sa.Column("decision_notes", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("access_mode IN ('api', 'dump', 'html')", name="ck_source_access_policy_mode"),
        sa.CheckConstraint("decision IN ('allowed', 'denied', 'review_required')", name="ck_source_access_policy_decision"),
    )
    op.create_table(
        "raw_ingestion_runs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("access_policy_id", _uuid(), sa.ForeignKey("source_access_policies.id")),
        sa.Column("adapter_name", sa.String(length=120), nullable=False),
        sa.Column("adapter_version", sa.String(length=100), nullable=False),
        sa.Column("manifest_uri", sa.String(length=800)),
        sa.Column("manifest_hash", sa.String(length=64)),
        sa.Column("input_revision", sa.String(length=150)),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("records_requested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_snapshotted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("status IN ('queued', 'running', 'complete', 'failed', 'cancelled')", name="ck_raw_ingestion_run_status"),
    )
    op.create_table(
        "source_objects",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("external_id", sa.String(length=300), nullable=False),
        sa.Column("object_kind", sa.String(length=80), nullable=False, server_default="work"),
        sa.Column("canonical_url", sa.String(length=800), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("source_id", "external_id", name="uq_source_object_source_external"),
    )
    op.create_table(
        "source_snapshots",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_object_id", _uuid(), sa.ForeignKey("source_objects.id"), nullable=False),
        sa.Column("ingestion_run_id", _uuid(), sa.ForeignKey("raw_ingestion_runs.id")),
        sa.Column("source_revision", sa.String(length=150)),
        sa.Column("canonical_url", sa.String(length=800), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fetch_status", sa.String(length=30), nullable=False, server_default="success"),
        sa.Column("http_status", sa.Integer()),
        sa.Column("media_type", sa.String(length=120)),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer()),
        sa.Column("storage_uri", sa.String(length=1000)),
        sa.Column("license", sa.String(length=100), nullable=False),
        sa.Column("attribution_url", sa.String(length=800)),
        sa.Column("parser_version", sa.String(length=100)),
        sa.UniqueConstraint("source_object_id", "source_revision", "content_hash", name="uq_source_snapshot_revision_hash"),
        sa.CheckConstraint("fetch_status IN ('success', 'not_modified', 'not_found', 'denied', 'failed')", name="ck_source_snapshot_fetch_status"),
    )
    op.create_table(
        "source_assertions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_snapshot_id", _uuid(), sa.ForeignKey("source_snapshots.id"), nullable=False),
        sa.Column("statement_locator", sa.String(length=500), nullable=False),
        sa.Column("source_property", sa.String(length=100)),
        sa.Column("raw_subject", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("raw_value", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("raw_qualifiers", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source_rank", sa.String(length=30)),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("source_snapshot_id", "statement_locator", "extractor_version", name="uq_source_assertion_locator"),
    )
    op.create_table(
        "entity_resolutions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_object_id", _uuid(), sa.ForeignKey("source_objects.id"), nullable=False),
        sa.Column("source_snapshot_id", _uuid(), sa.ForeignKey("source_snapshots.id")),
        sa.Column("entity_id", _uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("method", sa.String(length=80), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="review_required"),
        sa.Column("reviewer", sa.String(length=120)),
        sa.Column("rationale", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("source_object_id", "entity_id", "source_snapshot_id", name="uq_entity_resolution"),
        sa.CheckConstraint("status IN ('resolved', 'review_required', 'rejected')", name="ck_entity_resolution_status"),
    )
    op.create_table(
        "claims",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("subject_entity_id", _uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("predicate", sa.String(length=100), nullable=False),
        sa.Column("object_entity_id", _uuid(), sa.ForeignKey("canonical_entities.id")),
        sa.Column("object_entity_kind", sa.String(length=40)),
        sa.Column("value_json", sa.JSON()),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.Column("value_precision", sa.String(length=30)),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="raw"),
        sa.Column("normalization_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("object_entity_id IS NOT NULL OR value_json IS NOT NULL", name="ck_claim_has_target"),
        sa.CheckConstraint("status IN ('raw', 'resolved', 'published', 'review_required', 'retracted')", name="ck_claim_status"),
    )
    op.create_table(
        "claim_evidence",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("claim_id", _uuid(), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("source_assertion_id", _uuid(), sa.ForeignKey("source_assertions.id"), nullable=False),
        sa.Column("evidence_note", sa.Text()),
        sa.UniqueConstraint("claim_id", "source_assertion_id", name="uq_claim_evidence"),
    )
    op.create_table(
        "claim_qualifiers",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("claim_id", _uuid(), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("qualifier_key", sa.String(length=80), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("value_hash", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("claim_id", "qualifier_key", "value_hash", name="uq_claim_qualifier"),
    )
    for table, columns in {
        "source_access_policies": ["source_id"],
        "raw_ingestion_runs": ["source_id", "access_policy_id", "manifest_hash"],
        "source_objects": ["source_id", "external_id"],
        "source_snapshots": ["source_object_id", "ingestion_run_id", "source_revision", "content_hash"],
        "source_assertions": ["source_snapshot_id", "source_property"],
        "entity_resolutions": ["source_object_id", "source_snapshot_id", "entity_id"],
        "claims": ["subject_entity_id", "predicate", "object_entity_id", "object_entity_kind", "status"],
        "claim_evidence": ["claim_id", "source_assertion_id"],
        "claim_qualifiers": ["claim_id", "qualifier_key"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in [
        "claim_qualifiers", "claim_evidence", "claims", "entity_resolutions", "source_assertions",
        "source_snapshots", "source_objects", "raw_ingestion_runs", "source_access_policies",
    ]:
        op.drop_table(table)
