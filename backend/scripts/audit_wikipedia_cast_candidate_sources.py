"""Hash-check retained English Wikipedia captures and candidate passage bindings."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikipedia_cast_candidate_source_audit import (
    candidate_audit_summary,
    passage_binding_errors,
    sha256,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_ROOT = PROJECT_ROOT / "data" / "evaluation"


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Input must be a regular non-symlink file: {path}")
    resolved = path.resolve(strict=True)
    if EVALUATION_ROOT.resolve(strict=True) not in resolved.parents:
        raise ValueError("Audit inputs must remain under project data/evaluation")
    payload = resolved.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError(f"Input JSON root must be an object: {path}")
    return value, payload


def _read_bundle_file(bundle: Path, relative: str) -> bytes:
    relative_path = PurePosixPath(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"Unsafe bundle-relative path: {relative}")
    path = bundle
    for part in relative_path.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Symlinked bundle path is not allowed: {relative}")
    resolved = path.resolve(strict=True)
    if bundle.resolve(strict=True) not in resolved.parents or not resolved.is_file():
        raise ValueError(f"Bundle path is not a regular file inside the bundle: {relative}")
    return resolved.read_bytes()


def audit_partition(
    capture_path: Path, candidate_path: Path, extraction_path: Path | None = None,
) -> dict[str, Any]:
    capture, capture_bytes = _read_json(capture_path)
    candidates, candidate_bytes = _read_json(candidate_path)
    if capture.get("schema") != "cinegraph.catalog-pilot-capture/v1":
        raise ValueError(f"Unexpected capture manifest schema: {capture_path}")
    if candidates.get("schema") != "cinegraph.wikipedia-cast-candidates/v8":
        raise ValueError(f"Unexpected cast candidate schema: {candidate_path}")
    capture_hash = sha256(capture_bytes)
    candidate_hash = sha256(candidate_bytes)
    if candidates.get("film_capture_manifest_sha256") != capture_hash:
        raise ValueError("Candidate report is not bound to the exact capture-manifest bytes")
    if candidates.get("selection_sha256") != capture.get("selection_sha256"):
        raise ValueError("Candidate report and capture manifest selections differ")
    extraction_hash = candidates.get("passage_extraction_manifest_sha256")
    if extraction_hash is not None:
        if extraction_path is None:
            raise ValueError("Candidate report requires its exact passage-extraction manifest")
        extraction, extraction_bytes = _read_json(extraction_path)
        if sha256(extraction_bytes) != extraction_hash:
            raise ValueError("Candidate report is not bound to the exact passage-extraction manifest bytes")
        if (extraction.get("schema") != "cinegraph.catalog-pilot-extraction/v1"
                or extraction.get("selection_sha256") != capture.get("selection_sha256")):
            raise ValueError("Passage-extraction manifest schema or selection does not match the capture")
        extraction_films = extraction.get("films")
        if not isinstance(extraction_films, list):
            raise ValueError("Passage-extraction manifest has no films array")
        extracted_by_qid = {row.get("qid"): row for row in extraction_films if isinstance(row, dict)}
        if len(extracted_by_qid) != len(extraction_films):
            raise ValueError("Passage-extraction manifest contains duplicate/malformed film identities")
    else:
        if extraction_path is not None:
            raise ValueError("An extraction manifest was supplied but the candidate report does not bind one")
        extracted_by_qid = {}
    bundle = capture_path.parent.resolve(strict=True)
    capture_films = capture.get("films")
    candidate_films = candidates.get("films")
    candidate_rows = candidates.get("candidates")
    quarantined_rows = candidates.get("ambiguities")
    if not all(isinstance(value, list) for value in (capture_films, candidate_films, candidate_rows, quarantined_rows)):
        raise ValueError("Capture and candidate manifests must contain film, candidate and ambiguity arrays")
    if candidates.get("operational_fact_write") is not False:
        raise ValueError("Candidate source audit accepts only review-only candidate reports")
    candidate_summary = candidates.get("summary")
    if (not isinstance(candidate_summary, dict)
            or candidate_summary.get("films") != len(candidate_films)
            or candidate_summary.get("candidate_rows") != len(candidate_rows)
            or candidate_summary.get("ambiguous_or_unmatched_rows") != len(quarantined_rows)):
        raise ValueError("Candidate report summary counts do not match retained rows")

    capture_by_qid = {row.get("qid"): row for row in capture_films if isinstance(row, dict)}
    candidate_by_qid = {row.get("film_qid"): row for row in candidate_films if isinstance(row, dict)}
    if len(capture_by_qid) != len(capture_films) or len(candidate_by_qid) != len(candidate_films):
        raise ValueError("Capture or candidate manifest contains duplicate/malformed film identities")
    if set(capture_by_qid) != set(candidate_by_qid):
        raise ValueError("Capture and candidate film identity sets differ")
    if extraction_hash is not None and set(extracted_by_qid) != set(capture_by_qid):
        raise ValueError("Passage-extraction and capture film identity sets differ")
    errors: Counter[str] = Counter()
    passage_maps: dict[str, dict[tuple[str, int], dict[str, Any]]] = {}
    snapshots_verified = derivatives_verified = 0
    for qid, film in capture_by_qid.items():
        try:
            if (film.get("capture_status") != "complete"
                    or film.get("identity_status") != "verified"
                    or film.get("wikipedia_status") != "captured"
                    or film.get("wikipedia_license") != "CC BY-SA 4.0"
                    or film.get("wikipedia_attribution_url") != film.get("wikipedia_capture_url")):
                errors["capture_source_policy_or_identity_failure"] += 1
            source_bytes = _read_bundle_file(bundle, film["wikipedia_snapshot_path"])
            if len(source_bytes) != film.get("wikipedia_bytes") or sha256(source_bytes) != film.get("wikipedia_sha256"):
                errors["article_snapshot_integrity_failure"] += 1
            else:
                snapshots_verified += 1
            extraction_row = extracted_by_qid.get(qid)
            if extraction_hash is not None:
                if not isinstance(extraction_row, dict):
                    errors["passage_extraction_film_missing"] += 1
                    continue
                if (extraction_row.get("source_snapshot_sha256") != film.get("wikipedia_sha256")
                        or extraction_row.get("source_revision") != film.get("wikipedia_revision")
                        or extraction_row.get("canonical_url") != film.get("wikipedia_attribution_url")):
                    errors["passage_extraction_source_binding_failure"] += 1
                    continue
                derivative_path = extraction_row.get("passage_derivative_path")
                derivative_hash = extraction_row.get("passage_derivative_sha256")
                parser_version = extraction_row.get("parser_version")
            else:
                derivative_path = film.get("passage_derivative_path")
                derivative_hash = film.get("passage_derivative_sha256")
                parser_version = film.get("parser_version")
            derivative_bytes = _read_bundle_file(bundle, derivative_path)
            if sha256(derivative_bytes) != derivative_hash:
                errors["passage_derivative_integrity_failure"] += 1
                continue
            derivative = json.loads(derivative_bytes)
            if (derivative.get("schema") not in {
                    "cinegraph.wikipedia-passage-extraction/v4",
                    "cinegraph.wikipedia-passage-extraction/v6",
                    "cinegraph.wikipedia-passage-extraction/6",
                }
                    or derivative.get("parser_version") != parser_version
                    or derivative.get("source_revision") != film.get("wikipedia_revision")
                    or derivative.get("source_snapshot_sha256") != film.get("wikipedia_sha256")):
                errors["passage_derivative_source_binding_failure"] += 1
                continue
            passages = derivative.get("passages")
            if not isinstance(passages, list):
                errors["passage_derivative_schema_failure"] += 1
                continue
            passage_map: dict[tuple[str, int], dict[str, Any]] = {}
            for passage in passages:
                if not isinstance(passage, dict) or not isinstance(passage.get("section_locator"), str):
                    errors["passage_derivative_schema_failure"] += 1
                    continue
                key = (passage["section_locator"], passage.get("ordinal"))
                content = passage.get("content")
                if (not isinstance(key[1], int) or isinstance(key[1], bool)
                        or not isinstance(content, str)
                        or passage.get("content_sha256") != sha256(content.encode("utf-8"))):
                    errors["passage_content_integrity_failure"] += 1
                    continue
                if key in passage_map:
                    errors["duplicate_passage_locator"] += 1
                    continue
                passage_map[key] = passage
            passage_maps[qid] = passage_map
            derivatives_verified += 1
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            errors["capture_file_unavailable_or_invalid"] += 1

    def count_rows(rows: list[Any]) -> int:
        verified = 0
        for row in rows:
            if not isinstance(row, dict):
                errors["candidate_row_malformed"] += 1
                continue
            qid = row.get("film_qid")
            film = capture_by_qid.get(qid)
            passages = passage_maps.get(qid, {})
            key = (row.get("section_locator"), row.get("passage_ordinal"))
            passage = passages.get(key)
            if film is None:
                row_errors = ["candidate_film_missing"]
            elif passage is None:
                row_errors = ["candidate_passage_missing"]
            else:
                row_errors = passage_binding_errors(row, film, passage)
            if row_errors:
                errors.update(row_errors)
            else:
                verified += 1
        return verified

    candidate_verified = count_rows(candidate_rows)
    quarantined_verified = count_rows(quarantined_rows)
    summary = candidate_audit_summary(
        capture_manifest_sha256=capture_hash,
        candidate_report_sha256=candidate_hash,
        films=len(capture_films),
        snapshots_verified=snapshots_verified,
        passage_derivatives_verified=derivatives_verified,
        candidate_rows=len(candidate_rows),
        candidate_rows_verified=candidate_verified,
        quarantined_rows=len(quarantined_rows),
        quarantined_rows_verified=quarantined_verified,
        error_counts=errors,
    )
    summary["passage_extraction_manifest_sha256"] = extraction_hash
    summary["selection_sha256"] = capture.get("selection_sha256")
    summary["source_phrase_truth_claimed"] = False
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-manifest", type=Path, action="append", required=True)
    parser.add_argument("--candidate-report", type=Path, action="append", required=True)
    parser.add_argument(
        "--passage-extraction-manifest", type=Path, action="append",
        help="Exact extraction manifest for each candidate report that binds one; omit for partitions with none",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.capture_manifest) != len(args.candidate_report):
        parser.error("Each candidate report must be paired with its capture manifest")
    output = args.output.resolve()
    if args.output.is_symlink() or EVALUATION_ROOT.resolve(strict=True) not in output.parents:
        parser.error("Output must be a non-symlink file under project data/evaluation")
    extraction_paths = iter(args.passage_extraction_manifest or [])
    partitions = []
    for capture, candidate in zip(args.capture_manifest, args.candidate_report):
        candidate_value, _candidate_bytes = _read_json(candidate)
        extraction_path = (next(extraction_paths, None)
                           if candidate_value.get("passage_extraction_manifest_sha256") is not None else None)
        partitions.append(audit_partition(capture, candidate, extraction_path))
    if next(extraction_paths, None) is not None:
        parser.error("Too many passage-extraction manifests were supplied")
    total_errors: Counter[str] = Counter()
    for partition in partitions:
        total_errors.update(partition["error_counts"])
    report = {
        "schema": "cinegraph.wikipedia-cast-candidate-source-audit/v1",
        "partitions": partitions,
        "summary": {
            "films": sum(item["films"] for item in partitions),
            "article_snapshots_verified": sum(item["article_snapshots_verified"] for item in partitions),
            "passage_derivatives_verified": sum(item["passage_derivatives_verified"] for item in partitions),
            "candidate_rows": sum(item["candidate_rows"] for item in partitions),
            "candidate_source_bindings_verified": sum(item["candidate_source_bindings_verified"] for item in partitions),
            "quarantined_rows": sum(item["quarantined_rows"] for item in partitions),
            "quarantined_source_bindings_verified": sum(item["quarantined_source_bindings_verified"] for item in partitions),
            "error_counts": dict(sorted(total_errors.items())),
            "status": "passed" if all(part["status"] == "passed" for part in partitions) else "failed",
            "source_phrase_truth_claimed": False,
        },
    }
    payload = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    _write_immutable(output, payload)
    print(json.dumps({**report["summary"], "report_sha256": hashlib.sha256(payload).hexdigest(), "output": str(output)}, sort_keys=True))
    if report["summary"]["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
