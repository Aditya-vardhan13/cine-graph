"""Bounded, resumable capture of known Wikidata credit-label candidates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from app.core.config import get_settings
from app.services.catalog_pilot_reextract import _write_immutable
from app.services.credit_target_manifest import QID
from app.services.wikidata_raw import WikidataEntityDataFetcher


def save_checkpoint(path: Path, state: dict) -> None:
    payload = (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temp_path = Path(temporary.name)
        try:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("Batch limit must be between 1 and 50")
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != "cinegraph.credit-target-manifest/v1":
        raise ValueError("Unexpected credit-target manifest schema")
    qids = [row["qid"] for row in manifest["targets"]]
    if len(qids) != len(set(qids)) or any(not isinstance(q, str) or not QID.fullmatch(q) for q in qids):
        raise ValueError("Manifest contains duplicate or invalid QIDs")
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output / "checkpoint.json"
    with (args.output / "capture.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {"manifest_sha256": digest, "captured": {}}
        if state.get("manifest_sha256") != digest:
            raise ValueError("Checkpoint belongs to a different target manifest")
        captured = state["captured"]
        if not set(captured).issubset(qids):
            raise ValueError("Checkpoint contains unknown QIDs")
        for qid, row in captured.items():
            if not isinstance(row.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
                raise ValueError(f"Invalid stored snapshot hash for {qid}")
            expected = Path("snapshots") / qid / f"{row['sha256']}.json"
            if row["snapshot_path"] != expected.as_posix() or hashlib.sha256((args.output / expected).read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"Stored snapshot integrity failed for {qid}")
        pending = [qid for qid in qids if qid not in captured][:args.limit]
        if pending:
            with WikidataEntityDataFetcher(user_agent=get_settings().wikidata_user_agent) as fetcher:
                for qid in pending:
                    capture = fetcher.fetch(qid)
                    if not capture.entity.get("lastrevid"):
                        raise ValueError(f"Missing source revision for {qid}")
                    sha = hashlib.sha256(capture.payload).hexdigest()
                    relative = Path("snapshots") / qid / f"{sha}.json"
                    _write_immutable(args.output / relative, capture.payload)
                    label = capture.entity.get("labels", {}).get("en", {}).get("value")
                    captured[qid] = {"source_url": capture.canonical_url, "source_revision": capture.entity["lastrevid"],
                                     "retrieved_at": datetime.now(timezone.utc).isoformat(), "robots_sha256": fetcher.robots_sha256,
                                     "sha256": sha, "snapshot_path": relative.as_posix(), "english_label": label}
                    save_checkpoint(checkpoint, state)
                    print(f"captured {qid}: {len(captured)}/{len(qids)}", flush=True)
        print(f"captured total: {len(captured)}/{len(qids)}; remaining: {len(qids) - len(captured)}")


if __name__ == "__main__":
    main()
