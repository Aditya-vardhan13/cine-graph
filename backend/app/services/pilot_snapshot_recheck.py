"""Recheck previously unmapped pilot snapshots in the current local namespace."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app.services.snapshot_integrity import verify_snapshot_file


class PilotSnapshotRecheckError(ValueError):
    """The retained metadata audit cannot be safely rechecked."""


def recheck_unmapped_pilot_snapshots(
    audit: dict[str, Any], *, audit_sha256: str, allowed_snapshot_root: Path,
) -> dict[str, Any]:
    """Verify exact bytes only for snapshots the prior audit marked unmapped.

    This is a local-namespace diagnostic, not a database update or replacement
    for the original audit. A file is reported verified only when its recorded
    size and SHA-256 match exactly.
    """
    if (not isinstance(audit, dict)
            or not isinstance(audit.get("version"), str)
            or not isinstance(audit.get("film_count"), int)
            or not isinstance(audit.get("films"), list)
            or audit["film_count"] != len(audit["films"])):
        raise PilotSnapshotRecheckError("Expected a complete retained pilot metadata audit.")
    if (not isinstance(audit_sha256, str) or len(audit_sha256) != 64
            or any(char not in "0123456789abcdef" for char in audit_sha256)):
        raise PilotSnapshotRecheckError("Input audit SHA-256 is malformed.")

    snapshots: dict[str, dict[str, Any]] = {}
    for film in audit["films"]:
        if not isinstance(film, dict) or not isinstance(film.get("source_assertions"), dict):
            raise PilotSnapshotRecheckError("Pilot audit contains a malformed film or assertion collection.")
        for assertions in film["source_assertions"].values():
            if not isinstance(assertions, list):
                raise PilotSnapshotRecheckError("Pilot audit contains a malformed assertion list.")
            for assertion in assertions:
                if not isinstance(assertion, dict) or not isinstance(assertion.get("source_evidence"), list):
                    raise PilotSnapshotRecheckError("Pilot audit contains malformed source evidence.")
                for evidence in assertion["source_evidence"]:
                    if not isinstance(evidence, dict) or evidence.get("snapshot_integrity_status") != "unmapped":
                        continue
                    snapshot_id = evidence.get("snapshot_id")
                    uri = evidence.get("snapshot_storage_uri")
                    digest = evidence.get("snapshot_hash")
                    size = evidence.get("snapshot_byte_size")
                    if (not isinstance(snapshot_id, str) or not snapshot_id
                            or not isinstance(uri, str) or not isinstance(digest, str)
                            or not isinstance(size, int) or isinstance(size, bool) or size < 0):
                        raise PilotSnapshotRecheckError("An unmapped snapshot lacks exact integrity metadata.")
                    item = {
                        "snapshot_id": snapshot_id,
                        "film_title": film.get("input_title"),
                        "wikidata_id": film.get("wikidata_id"),
                        "storage_uri": uri,
                        "sha256": digest,
                        "byte_size": size,
                    }
                    prior = snapshots.setdefault(snapshot_id, item)
                    if prior != item:
                        raise PilotSnapshotRecheckError(
                            f"Snapshot {snapshot_id} has inconsistent retained audit metadata."
                        )

    root = allowed_snapshot_root.resolve(strict=False)
    if not root.is_dir():
        raise PilotSnapshotRecheckError("The allowed local snapshot root must exist as a directory.")

    rows = []
    for snapshot_id in sorted(snapshots):
        item = snapshots[snapshot_id]
        rows.append({
            **item,
            "previous_status": "unmapped",
            "local_recheck_status": verify_snapshot_file(
                item["storage_uri"], item["sha256"], item["byte_size"],
                root_mappings=((root, root),),
            ),
        })
    counts = Counter(row["local_recheck_status"] for row in rows)
    return {
        "schema": "cinegraph.pilot-snapshot-local-recheck/v1",
        "input_audit_version": audit["version"],
        "input_audit_sha256": audit_sha256,
        "pilot_film_count": audit["film_count"],
        "allowed_snapshot_root": str(root),
        "previously_unmapped_snapshot_count": len(rows),
        "local_recheck_status_counts": dict(sorted(counts.items())),
        "snapshots": rows,
        "limitations": [
            "Rechecks only snapshots previously marked unmapped; it does not replace or mutate the original audit.",
            "A verified local byte file proves size and digest only, not factual accuracy, source eligibility, or publication rights.",
            "URIs outside the allowed root remain unmapped and are not opened; no source is fetched, repaired, or copied.",
        ],
    }
