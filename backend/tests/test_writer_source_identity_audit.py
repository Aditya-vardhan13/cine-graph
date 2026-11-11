import hashlib
import json

import pytest

from app.models import SourceSnapshot
from scripts.audit_writer_source_identity import read_snapshot, wiki_title


def test_only_english_wikipedia_article_urls_are_accepted():
    assert wiki_title("https://en.wikipedia.org/wiki/Avengers:_Endgame") == "Avengers: Endgame"
    assert wiki_title("https://en.wikipedia.org/wiki/Am%C3%A9lie") == "Amélie"
    assert wiki_title("https://example.org/wiki/The_Godfather") is None
    assert wiki_title("http://en.wikipedia.org/wiki/The_Godfather") is None


def test_retained_snapshot_requires_matching_content_hash_and_size(tmp_path):
    content = json.dumps({"id": "Q42"}).encode()
    path = tmp_path / "retained.json"
    path.write_bytes(content)
    snapshot = SourceSnapshot(storage_uri=path.as_uri(), content_hash=hashlib.sha256(content).hexdigest(),
                              byte_size=len(content), canonical_url="https://en.wikipedia.org/wiki/Test",
                              license="CC BY-SA 4.0")
    assert read_snapshot(snapshot)["id"] == "Q42"
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="snapshot_integrity_failed"):
        read_snapshot(snapshot)
