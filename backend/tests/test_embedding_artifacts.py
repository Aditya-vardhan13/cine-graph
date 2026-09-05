from app.services.embedding_artifacts import document_cache_key, embedding_configuration_hash


def test_document_cache_key_changes_when_source_derived_content_changes() -> None:
    base = dict(
        provider="ollama",
        model_name="qwen3-embedding:0.6b",
        dimensions=1024,
        chunk_run_id="run-1",
        chunker_version="chunker-v1",
    )

    first = document_cache_key(**base, contents=["first passage"])
    changed = document_cache_key(**base, contents=["changed passage"])

    assert first != changed
    assert first == document_cache_key(**base, contents=["first passage"])


def test_index_configuration_includes_model_revision_and_instruction() -> None:
    first = embedding_configuration_hash(
        model_name="qwen3-embedding:0.6b", model_revision="digest-a",
        dimension=1024, instruction_hash="instruction-a",
    )

    assert first != embedding_configuration_hash(
        model_name="qwen3-embedding:0.6b", model_revision="digest-b",
        dimension=1024, instruction_hash="instruction-a",
    )
    assert first != embedding_configuration_hash(
        model_name="qwen3-embedding:0.6b", model_revision="digest-a",
        dimension=1024, instruction_hash="instruction-b",
    )
