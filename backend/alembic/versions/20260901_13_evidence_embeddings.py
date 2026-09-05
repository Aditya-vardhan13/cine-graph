"""Add versioned pgvector evidence indexes.

Vectors nominate evidence passages. They do not create assertions or graph
edges, and every row remains tied to the exact source-derived evidence chunk.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "20260901_13"
down_revision: Union[str, None] = "20260816_12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "embedding_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("model_revision", sa.String(length=160), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("query_instruction", sa.Text(), nullable=False),
        sa.Column("instruction_hash", sa.String(length=64), nullable=False),
        sa.Column("license", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("dimension = 1024", name="ck_embedding_model_storage_dimension"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "model_name", "model_revision", "dimension", "instruction_hash",
            name="uq_embedding_model_contract",
        ),
    )
    op.create_table(
        "embedding_index_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_chunk_run_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_model_id", sa.Uuid(), nullable=False),
        sa.Column("document_representation", sa.String(length=100), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("chunks_requested", sa.Integer(), nullable=False),
        sa.Column("chunks_completed", sa.Integer(), nullable=False),
        sa.Column("chunks_failed", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('running', 'complete', 'failed')", name="ck_embedding_index_run_status"),
        sa.ForeignKeyConstraint(["embedding_model_id"], ["embedding_models.id"]),
        sa.ForeignKeyConstraint(["evidence_chunk_run_id"], ["evidence_chunk_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_chunk_run_id", "embedding_model_id", "configuration_hash",
            name="uq_embedding_index_run_contract",
        ),
    )
    op.create_index("ix_embedding_index_runs_evidence_chunk_run_id", "embedding_index_runs", ["evidence_chunk_run_id"])
    op.create_index("ix_embedding_index_runs_embedding_model_id", "embedding_index_runs", ["embedding_model_id"])
    op.create_index("ix_embedding_index_runs_configuration_hash", "embedding_index_runs", ["configuration_hash"])
    op.create_table(
        "evidence_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("index_run_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["evidence_chunk_id"], ["evidence_chunks.id"]),
        sa.ForeignKeyConstraint(["index_run_id"], ["embedding_index_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_run_id", "evidence_chunk_id", name="uq_evidence_embedding_run_chunk"),
    )
    op.create_index("ix_evidence_embeddings_index_run_id", "evidence_embeddings", ["index_run_id"])
    op.create_index("ix_evidence_embeddings_evidence_chunk_id", "evidence_embeddings", ["evidence_chunk_id"])
    op.create_index("ix_evidence_embeddings_content_hash", "evidence_embeddings", ["content_hash"])
    op.create_index(
        "ix_evidence_embeddings_embedding_hnsw",
        "evidence_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("evidence_embeddings")
    op.drop_table("embedding_index_runs")
    op.drop_table("embedding_models")
