"""Validate newly captured identity observations without promoting them."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

from app.services.wikidata_raw import RawWikidataError, entity_from_entitydata, entitydata_url
from scripts.capture_writer_identity_recovery import CHECKPOINT_SCHEMA, recovery_targets, local_output


def review_signals(entity: dict) -> dict:
    """Expose source-stated hints, not reviewed operational facts."""
    claims = entity.get("claims") or {}

    def values(property_id: str) -> list[dict]:
        results = []
        for claim in claims.get(property_id, []):
            if claim.get("rank") == "deprecated":
                continue
            value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if isinstance(value, dict):
                results.append(value)
        return results

    def ids(property_id: str) -> list[str]:
        return sorted({v["id"] for v in values(property_id) if isinstance(v.get("id"), str)})

    years = set()
    for value in values("P577"):
        match = re.match(r"^\+(\d{4})-", str(value.get("time") or ""))
        if match and int(value.get("precision") or 0) >= 9:
            years.add(int(match.group(1)))
    english = (entity.get("labels", {}).get("en", {}) or {}).get("value")
    return {"english_label": english if isinstance(english, str) else None,
            "instance_of_ids": ids("P31"), "director_ids": ids("P57"),
            "original_language_ids": ids("P364"), "country_ids": ids("P495"),
            "release_year_candidates": sorted(years)}


def audit_recovery(audit_path: Path, recovery_dir: Path) -> dict:
    audit_bytes = audit_path.read_bytes()
    audit_hash = hashlib.sha256(audit_bytes).hexdigest()
    targets = recovery_targets(json.loads(audit_bytes))
    target_by_qid = {row["wikidata_id"]: row for row in targets}
    root = recovery_dir.resolve()
    state = json.loads((root / "checkpoint.json").read_bytes())
    if state.get("schema") != CHECKPOINT_SCHEMA or state.get("audit_sha256") != audit_hash:
        raise ValueError("Checkpoint does not match the exact identity audit.")
    captures = state.get("captures")
    if not isinstance(captures, dict) or set(captures) - set(target_by_qid):
        raise ValueError("Checkpoint contains unexpected or malformed capture identities.")
    entries = []
    counts = Counter()
    for qid, item in sorted(captures.items()):
        original = target_by_qid[qid]
        issues = []
        if (item.get("previous_snapshot_id"), item.get("previous_revision"), item.get("previous_sha256")) != (
            original.get("wikidata_snapshot_id"), original.get("wikidata_revision"), original.get("wikidata_sha256")
        ):
            issues.append("original_snapshot_reference_mismatch")
        expected_title = unquote(original["wikipedia_url"].split("/wiki/", 1)[-1]).replace("_", " ")
        if item.get("source_url") != entitydata_url(qid):
            issues.append("unexpected_capture_url")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("robots_sha256") or "")):
            issues.append("robots_fingerprint_missing")
        if item.get("identity_status") != "review_required" or item.get("product_ingested") is not False:
            issues.append("capture_not_marked_review_only")
        signals = None
        try:
            path = (root / item["snapshot_path"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("snapshot_path_outside_recovery")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != item.get("sha256"):
                raise ValueError("snapshot_hash_mismatch")
            entity = entity_from_entitydata(json.loads(payload), qid)
            signals = review_signals(entity)
            if str(entity.get("lastrevid")) != str(item.get("source_revision")):
                issues.append("new_revision_mismatch")
            title = (entity.get("sitelinks", {}).get("enwiki", {}) or {}).get("title")
            if title != expected_title:
                issues.append("new_sitelink_mismatch")
            if item.get("new_sitelink_title") != title or item.get("wikipedia_title") != expected_title:
                issues.append("checkpoint_title_mismatch")
        except (OSError, ValueError, TypeError, KeyError, RawWikidataError) as exc:
            issues.append("snapshot_unreadable_or_invalid:" + type(exc).__name__)
        entry = {"qid": qid, "film_title": original["film_title"],
                 "prior_revision": original.get("wikidata_revision"),
                 "new_revision": item.get("source_revision"), "new_sha256": item.get("sha256"),
                 "wikipedia_url": original["wikipedia_url"],
                 "mechanical_checks_passed": not issues, "issues": sorted(set(issues)),
                 "new_source_review_signals": signals,
                 "identity_status": "review_required", "rights_status": "review_required"}
        counts["captured"] += 1
        counts["mechanical_pass"] += int(not issues)
        if signals is not None:
            counts["source_has_direct_film_instance"] += int("Q11424" in signals["instance_of_ids"])
            counts["source_missing_direct_film_instance"] += int("Q11424" not in signals["instance_of_ids"])
            counts["source_missing_english_label"] += int(signals["english_label"] is None)
            counts["source_missing_director"] += int(not signals["director_ids"])
            counts["source_missing_release_year"] += int(not signals["release_year_candidates"])
        for issue in set(issues):
            counts[issue] += 1
        entries.append(entry)
    counts["targets"] = len(targets)
    counts["remaining"] = len(targets) - len(captures)
    return {"schema": "cinegraph.writer-identity-recovery-audit/v1", "audit_sha256": audit_hash,
            "complete": counts["remaining"] == 0, "review_status": "review_required",
            "note": "New snapshots are separate observations, not recovered historic bytes or approved facts.",
            "counts": dict(counts), "entries": entries}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("recovery_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = local_output(args.output)
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing recovery review report")
    report = audit_recovery(args.audit, local_output(args.recovery_dir))
    payload = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(json.dumps({"output": str(output), "sha256": hashlib.sha256(payload).hexdigest(), "counts": report["counts"]}))


if __name__ == "__main__":
    main()
