import pytest

from app.services.writer_catalog_index import recovery_profile


def test_recovery_profile_requires_immutable_large_model():
    digest = "a" * 64
    profile = recovery_profile("qwen3-embedding:4b", digest)
    assert profile.model == "qwen3-embedding:4b"
    assert profile.expected_model_digest == digest
    assert profile.dimensions == 1024
    with pytest.raises(ValueError, match="4B or 8B"):
        recovery_profile("qwen3-embedding:0.6b", digest)
    with pytest.raises(ValueError, match="SHA-256"):
        recovery_profile("qwen3-embedding:4b", "latest")
