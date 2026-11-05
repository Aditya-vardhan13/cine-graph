"""Capture at most two known Wikidata credit entities for an offline pilot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from app.core.config import get_settings
from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikidata_raw import WikidataEntityDataFetcher


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("qids", nargs="+")
    args = parser.parse_args()
    if not 1 <= len(args.qids) <= 2 or len(set(args.qids)) != len(args.qids):
        parser.error("Provide one or two distinct known QIDs")
    rows = []
    with WikidataEntityDataFetcher(user_agent=get_settings().wikidata_user_agent) as fetcher:
        for qid in args.qids:
            capture = fetcher.fetch(qid)
            digest = hashlib.sha256(capture.payload).hexdigest()
            path = Path("snapshots") / qid / f"{digest}.json"
            _write_immutable(args.output / path, capture.payload)
            rows.append({"qid": qid, "source_url": capture.canonical_url,
                         "retrieved_at": datetime.now(timezone.utc).isoformat(),
                         "source_revision": capture.entity.get("lastrevid"),
                         "sha256": digest, "snapshot_path": path.as_posix(),
                         "english_label": capture.entity.get("labels", {}).get("en", {}).get("value")})
        manifest = {"robots_sha256": fetcher.robots_sha256, "entities": rows}
    encoded = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    _write_immutable(args.output / "manifest.json", encoded)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
