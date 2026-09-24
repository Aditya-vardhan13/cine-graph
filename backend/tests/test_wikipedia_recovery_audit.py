import hashlib

from app.services.wikipedia_recovery_audit import passage_keys


def test_recovery_hashes_use_the_same_section_and_chunk_policy() -> None:
    text = "Lead.\n== Plot ==\nA [[Hero|hero]] acts.\n== References ==\nCitation only."
    expected = {
        ("lead", 0, hashlib.sha256("Lead.".encode()).hexdigest()),
        ("plot", 0, hashlib.sha256("A hero acts.".encode()).hexdigest()),
    }
    assert passage_keys(text) == expected
