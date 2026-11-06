"""Audit Wikipedia actor-role candidates against retained Wikidata P453 claims."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.credit_label_capture_audit import audit_credit_label_capture
from app.services.wikidata_cast_character_crosswalk import (
    build_wikidata_cast_character_crosswalk,
    render_wikidata_cast_character_crosswalk,
    render_wikidata_cast_character_review_html,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_ROOT = PROJECT_ROOT / "data" / "evaluation"


def _read_json(path: Path) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Input must be a regular non-symlink JSON file: {path}")
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Input JSON root must be an object: {path}")
    return value, raw


def _read_local(root: Path, relative: str) -> bytes:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Snapshot path must remain relative to its local capture root")
    candidate = root / Path(*path.parts)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"Snapshot must be a regular non-symlink file: {relative}")
    resolved_root = root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    if resolved_root not in resolved.parents:
        raise ValueError("Snapshot path escapes its local capture root")
    return resolved.read_bytes()


def _partition(candidate_path: Path, bundle: Path, targets_path: Path, label_dir: Path,
               extraction_path: Path | None) -> dict:
    candidate_report, candidate_bytes = _read_json(candidate_path)
    capture_path = bundle / "capture-manifest.json"
    capture, capture_bytes = _read_json(capture_path)
    targets, targets_bytes = _read_json(targets_path)
    checkpoint_path = label_dir / "checkpoint.json"
    checkpoint, checkpoint_bytes = _read_json(checkpoint_path)
    extraction = None
    extraction_bytes = None
    if extraction_path is not None:
        extraction, extraction_bytes = _read_json(extraction_path)

    resolved_eval = EVALUATION_ROOT.resolve(strict=True)
    paths = [candidate_path, bundle, targets_path, label_dir]
    if extraction_path is not None:
        paths.append(extraction_path)
    for path in paths:
        if resolved_eval not in path.resolve(strict=True).parents:
            raise ValueError("All retained inputs must remain under local data/evaluation")
    audit = audit_credit_label_capture(targets_path, label_dir)
    if audit.get("status") != "complete":
        raise ValueError("Credit-label capture audit is incomplete")

    candidate_rows = candidate_report.get("candidates", [])
    film_qids = {row.get("film_qid") for row in candidate_rows if isinstance(row, dict)}
    capture_by_qid = {row.get("qid"): row for row in capture.get("films", []) if isinstance(row, dict)}
    derivative_by_qid: dict[str, dict] = {}
    extraction_sha = candidate_report.get("passage_extraction_manifest_sha256")
    if extraction_sha:
        if extraction is None or hashlib.sha256(extraction_bytes).hexdigest() != extraction_sha:
            raise ValueError("Candidate report does not bind to the supplied passage-extraction manifest")
        if (extraction.get("schema") != "cinegraph.catalog-pilot-extraction/v1"
                or extraction.get("selection_sha256") != candidate_report.get("selection_sha256")):
            raise ValueError("Passage-extraction manifest has a different schema or pilot selection")
        extraction_films = extraction.get("films")
        if not isinstance(extraction_films, list):
            raise ValueError("Passage-extraction manifest has no film rows")
        derivative_by_qid = {row.get("qid"): row for row in extraction_films if isinstance(row, dict)}
        if len(derivative_by_qid) != len(extraction_films) or set(derivative_by_qid) != set(capture_by_qid):
            raise ValueError("Passage-extraction manifest does not cover the exact capture film set")
        for qid, source_film in capture_by_qid.items():
            derivative = derivative_by_qid[qid]
            if (derivative.get("source_snapshot_sha256") != source_film.get("wikipedia_sha256")
                    or derivative.get("source_revision") != source_film.get("wikipedia_revision")
                    or derivative.get("canonical_url") != source_film.get("wikipedia_attribution_url")
                    or derivative.get("parser_version") != "enwiki-article-html-extraction-v6"):
                raise ValueError(f"Passage extraction is not bound to captured article {qid}")
    else:
        derivative_by_qid = {
            qid: {
                "passage_derivative_path": row.get("passage_derivative_path"),
                "passage_derivative_sha256": row.get("passage_derivative_sha256"),
                "parser_version": row.get("parser_version"),
                "source_revision": row.get("wikipedia_revision"),
                "source_snapshot_sha256": row.get("wikipedia_sha256"),
            }
            for qid, row in capture_by_qid.items()
        }
    film_snapshots: dict[str, tuple[dict, bytes]] = {}
    passage_snapshots: dict[str, tuple[dict, bytes]] = {}
    passage_derivative_bindings: dict[str, dict] = {}
    for qid in film_qids:
        film = capture_by_qid.get(qid)
        if film is None or film.get("wikidata_status") != "captured":
            raise ValueError(f"Wikidata source snapshot is missing for candidate film {qid}")
        payload = _read_local(bundle, film["wikidata_snapshot_path"])
        film_snapshots[qid] = (json.loads(payload), payload)
        derivative = derivative_by_qid.get(qid)
        if derivative is None:
            raise ValueError(f"Wikipedia passage derivative is missing for candidate film {qid}")
        passage_payload = _read_local(bundle, derivative["passage_derivative_path"])
        passage_snapshots[qid] = (json.loads(passage_payload), passage_payload)
        passage_derivative_bindings[qid] = derivative

    possible_character_qids: set[str] = set()
    candidate_actor_locators = {
        (row.get("film_qid"), row.get("actor_qid")): set(row.get("actor_statement_locators", []))
        for row in candidate_rows if isinstance(row, dict) and row.get("actor_qid")
    }
    for target in targets.get("targets", []):
        if not isinstance(target, dict):
            continue
        for reference in target.get("references", []):
            if not isinstance(reference, dict) or reference.get("role") != "character":
                continue
            locators = candidate_actor_locators.get((reference.get("film_qid"), reference.get("person_qid")), set())
            if reference.get("statement_locator") in locators:
                possible_character_qids.add(target["qid"])

    captured = checkpoint.get("captured", {})
    label_snapshot_payloads: dict[str, bytes] = {}
    for qid in possible_character_qids:
        row = captured.get(qid)
        if not isinstance(row, dict):
            raise ValueError(f"Captured label is missing for candidate character {qid}")
        label_snapshot_payloads[qid] = _read_local(label_dir, row["snapshot_path"])

    return {
        "candidate_report": candidate_report,
        "capture_manifest": capture,
        "credit_target_manifest": targets,
        "label_checkpoint": checkpoint,
        "raw_bytes": {
            "candidate_report": candidate_bytes,
            "capture_manifest": capture_bytes,
            "credit_target_manifest": targets_bytes,
            "label_checkpoint": checkpoint_bytes,
        },
        "film_snapshots": film_snapshots,
        "passage_snapshots": passage_snapshots,
        "passage_derivative_bindings": passage_derivative_bindings,
        "label_snapshot_payloads": label_snapshot_payloads,
    }


def _write(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise ValueError(f"Output cannot be a symlink: {path}")
    resolved = path.resolve()
    if EVALUATION_ROOT.resolve(strict=True) not in resolved.parents:
        raise ValueError("Outputs must remain under local data/evaluation")
    _write_immutable(resolved, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-report", action="append", type=Path, required=True)
    parser.add_argument("--bundle-dir", action="append", type=Path, required=True,
                        help="Captured Wikipedia/Wikidata source bundle; repeat per partition")
    parser.add_argument("--credit-target-manifest", action="append", type=Path, required=True)
    parser.add_argument("--credit-label-dir", action="append", type=Path, required=True)
    parser.add_argument("--passage-extraction-manifest", action="append", type=Path, required=True,
                        help="Use '-' for partitions whose candidate report is bound directly to capture-manifest passages")
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--html-output", type=Path, required=True)
    args = parser.parse_args()
    lengths = {len(args.candidate_report), len(args.bundle_dir),
               len(args.credit_target_manifest), len(args.credit_label_dir),
               len(args.passage_extraction_manifest)}
    if len(lengths) != 1:
        parser.error("Repeat each of the four partition arguments the same number of times and in matching order")
    partitions = [
        _partition(candidate, bundle, targets, labels, None if str(extraction) == "-" else extraction)
        for candidate, bundle, targets, labels, extraction in zip(
            args.candidate_report, args.bundle_dir, args.credit_target_manifest,
            args.credit_label_dir, args.passage_extraction_manifest, strict=True,
        )
    ]
    report = build_wikidata_cast_character_crosswalk(partitions)
    json_payload = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    markdown_payload = render_wikidata_cast_character_crosswalk(report).encode()
    html_payload = render_wikidata_cast_character_review_html(report).encode()
    _write(args.json_output, json_payload)
    _write(args.markdown_output, markdown_payload)
    _write(args.html_output, html_payload)
    print(json.dumps({
        **report["summary"],
        "json_sha256": hashlib.sha256(json_payload).hexdigest(),
        "markdown_sha256": hashlib.sha256(markdown_payload).hexdigest(),
        "html_sha256": hashlib.sha256(html_payload).hexdigest(),
        "json_output": str(args.json_output),
        "markdown_output": str(args.markdown_output),
        "html_output": str(args.html_output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
