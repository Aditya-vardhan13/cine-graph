"""Prepare review-only cast candidates from the retained English 100-film pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.credit_label_capture_audit import audit_credit_label_capture
from app.services.wikipedia_cast_candidates import (
    ADAPTER_VERSION,
    extract_cast_candidates,
    resolve_source_actor_identities,
)


def _read_local_file(root: Path, relative: str) -> bytes:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Unsafe relative capture path: {relative}")
    path = root
    for part in candidate.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Symlinked capture path is not allowed: {relative}")
    resolved_root = root.resolve(strict=True)
    resolved_path = path.resolve(strict=True)
    if resolved_root not in resolved_path.parents or not resolved_path.is_file():
        raise ValueError(f"Capture path is not a regular file inside the bundle: {relative}")
    return resolved_path.read_bytes()


def _read_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Manifest must be a regular, non-symlink file: {path}")
    payload = path.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError(f"Manifest root must be an object: {path}")
    return value, payload


def _bind_extraction_manifest(
    capture_manifest: dict[str, Any], extraction_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    if extraction_manifest.get("schema") != "cinegraph.catalog-pilot-extraction/v1":
        raise ValueError("Unexpected pilot extraction manifest schema")
    if extraction_manifest.get("selection_sha256") != capture_manifest.get("selection_sha256"):
        raise ValueError("Capture and passage extraction manifests have different selections")
    capture_films = capture_manifest.get("films")
    extraction_films = extraction_manifest.get("films")
    if not isinstance(capture_films, list) or not isinstance(extraction_films, list):
        raise ValueError("Capture/extraction manifest has no films list")
    by_qid = {row.get("qid"): row for row in extraction_films if isinstance(row, dict)}
    if len(by_qid) != len(extraction_films) or set(by_qid) != {
        row.get("qid") for row in capture_films if isinstance(row, dict)
    }:
        raise ValueError("Capture and passage extraction film identities differ")
    bound = []
    for film in capture_films:
        if not isinstance(film, dict):
            raise ValueError("Capture manifest contains a malformed film row")
        extraction = by_qid[film["qid"]]
        if (extraction.get("source_snapshot_sha256") != film.get("wikipedia_sha256")
                or extraction.get("source_revision") != film.get("wikipedia_revision")
                or extraction.get("canonical_url") != film.get("wikipedia_attribution_url")
                or extraction.get("parser_version") != "enwiki-article-html-extraction-v6"
                or not isinstance(extraction.get("passage_derivative_path"), str)
                or not isinstance(extraction.get("passage_derivative_sha256"), str)):
            raise ValueError(f"Passage extraction is not bound to the captured article: {film.get('qid')}")
        bound.append({
            **film,
            "passage_derivative_path": extraction["passage_derivative_path"],
            "passage_derivative_sha256": extraction["passage_derivative_sha256"],
            "parser_version": extraction["parser_version"],
        })
    return bound


def _passage_derivative_binding(derivative: dict, film: dict) -> dict[str, bool]:
    """Validate retained v6 parser identity, including the original schema typo."""
    return {
        # Both exact markers occur in immutable v6 derivatives: /v6 in ranks
        # 1-10, /6 in ranks 11-100. Hash/revision/parser checks still bind each
        # payload to its exact captured article.
        "schema": derivative.get("schema") in {
            "cinegraph.wikipedia-passage-extraction/v6",
            "cinegraph.wikipedia-passage-extraction/6",
        },
        "parser_version": derivative.get("parser_version") == "enwiki-article-html-extraction-v6",
        "revision": derivative.get("source_revision") == film.get("wikipedia_revision"),
        "snapshot_sha256": derivative.get("source_snapshot_sha256") == film.get("wikipedia_sha256"),
    }


def prepare(
    bundle: Path, credit_manifest_path: Path, label_dir: Path,
    extraction_manifest_path: Path | None = None,
) -> dict[str, Any]:
    if bundle.is_symlink() or label_dir.is_symlink():
        raise ValueError("Capture bundle roots must not be symlinks")
    bundle = bundle.resolve(strict=True)
    capture_manifest_path = bundle / "capture-manifest.json"
    capture_manifest, capture_bytes = _read_manifest(capture_manifest_path)
    credit_manifest, credit_bytes = _read_manifest(credit_manifest_path)
    extraction_manifest = None
    extraction_bytes = None
    if extraction_manifest_path is not None:
        extraction_manifest, extraction_bytes = _read_manifest(extraction_manifest_path)
    if capture_manifest.get("schema") != "cinegraph.catalog-pilot-capture/v1":
        raise ValueError("Unexpected catalog-pilot capture manifest schema")
    if credit_manifest.get("schema") != "cinegraph.credit-target-manifest/v1":
        raise ValueError("Unexpected credit-target manifest schema")
    if capture_manifest.get("selection_sha256") != credit_manifest.get("selection_sha256"):
        raise ValueError("Film capture and credit-target manifests have different selections")

    label_dir = label_dir.resolve(strict=True)
    checkpoint_path = label_dir / "checkpoint.json"
    if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
        raise ValueError("Credit-label checkpoint must be a regular, non-symlink file")
    checkpoint_bytes = checkpoint_path.read_bytes()
    checkpoint = json.loads(checkpoint_bytes)
    audit = audit_credit_label_capture(credit_manifest_path, label_dir)
    if audit["status"] != "complete":
        raise ValueError("Credit-label capture audit did not complete")

    # The audit verifies hashes/IDs/revisions; this extra check rejects path
    # substitution through symlinks before those snapshots are used as labels.
    for qid, row in checkpoint["captured"].items():
        _read_local_file(label_dir, row["snapshot_path"])

    captured_films = capture_manifest.get("films")
    if not isinstance(captured_films, list):
        raise ValueError("Film capture manifest has no films list")
    if extraction_manifest is not None:
        captured_films = _bind_extraction_manifest(capture_manifest, extraction_manifest)
    film_by_qid = {row.get("qid"): row for row in captured_films if isinstance(row, dict)}
    if len(film_by_qid) != len(captured_films):
        raise ValueError("Film capture manifest contains duplicate or malformed QIDs")

    targets_by_film: dict[str, list[dict[str, Any]]] = {}
    character_targets_by_actor: dict[tuple[str, str], list[dict[str, str]]] = {}
    person_target_qids: set[str] = set()
    for target in credit_manifest.get("targets", []):
        qid = target.get("qid")
        if not isinstance(qid, str):
            raise ValueError("Credit-target row has no QID")
        for reference in target.get("references", []):
            film_qid, role = reference.get("film_qid"), reference.get("role")
            if film_qid not in film_by_qid:
                raise ValueError(f"Credit target references uncaptured film {film_qid}")
            if role == "cast":
                person_target_qids.add(qid)
                labels = checkpoint["captured"].get(qid, {}).get("english_label")
                if isinstance(labels, str) and labels.strip():
                    targets_by_film.setdefault(film_qid, []).append({
                        "qid": qid, "label": labels,
                        "statement_locators": [reference["statement_locator"]],
                    })
            elif role == "character":
                person_qid = reference.get("person_qid")
                label = checkpoint["captured"].get(qid, {}).get("english_label")
                if isinstance(person_qid, str) and isinstance(label, str) and label.strip():
                    character_targets_by_actor.setdefault((film_qid, person_qid), []).append(
                        {"qid": qid, "label": label}
                    )
            elif role in {"director", "writer"}:
                person_target_qids.add(qid)

    captured_people: list[dict[str, Any]] = []
    for person_qid in sorted(person_target_qids):
        captured = checkpoint["captured"][person_qid]
        label = captured.get("english_label")
        if not isinstance(label, str) or not label.strip():
            continue
        source_bytes = _read_local_file(label_dir, captured["snapshot_path"])
        entity_data = json.loads(source_bytes)
        entities = entity_data.get("entities", {})
        entity = entities.get(person_qid, {}) if isinstance(entities, dict) else {}
        entity_aliases = entity.get("aliases", {}) if isinstance(entity, dict) else {}
        english_aliases = entity_aliases.get("en", []) if isinstance(entity_aliases, dict) else []
        aliases = [
            value.get("value") for value in english_aliases
            if isinstance(value, dict) and isinstance(value.get("value"), str)
        ]
        captured_people.append({
            "qid": person_qid,
            "label": label,
            "aliases": aliases,
            "source_url": captured.get("source_url"),
            "source_revision": captured.get("source_revision"),
            "snapshot_sha256": captured.get("sha256"),
        })

    film_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    ambiguity_rows: list[dict[str, Any]] = []
    for film in sorted(captured_films, key=lambda row: (row.get("selection_rank", 0), row.get("qid", ""))):
        qid = film.get("qid")
        if (film.get("identity_status") != "verified" or film.get("capture_status") != "complete"
                or film.get("wikipedia_status") != "captured"):
            raise ValueError(f"Film source identity/capture is not verified: {qid}")
        attribution_url = film.get("wikipedia_attribution_url")
        parsed_url = urlparse(attribution_url) if isinstance(attribution_url, str) else None
        if (film.get("wikipedia_license") != "CC BY-SA 4.0" or parsed_url is None
                or parsed_url.scheme != "https" or parsed_url.hostname != "en.wikipedia.org"
                or not parsed_url.path.startswith("/wiki/")):
            raise ValueError(f"Wikipedia attribution/license metadata is incomplete for {qid}")
        derivative_path = film.get("passage_derivative_path")
        payload = _read_local_file(bundle, derivative_path)
        derivative_hash = hashlib.sha256(payload).hexdigest()
        if derivative_hash != film.get("passage_derivative_sha256"):
            raise ValueError(f"Passage derivative hash mismatch for {qid}")
        derivative = json.loads(payload)
        binding = _passage_derivative_binding(derivative, film)
        if not all(binding.values()):
            raise ValueError(f"Passage derivative source binding mismatch for {qid}: {binding}")
        result = extract_cast_candidates(
            film_qid=qid,
            passages=derivative.get("passages", []),
            actors=targets_by_film.get(qid, []),
            character_labels_by_actor={
                actor["qid"]: character_targets_by_actor.get((qid, actor["qid"]), [])
                for actor in targets_by_film.get(qid, [])
            },
        )
        identity_candidates = resolve_source_actor_identities(
            result["candidates"], captured_people,
        )
        for candidate in identity_candidates:
            candidate_rows.append({
                **candidate,
                "selection_rank": film.get("selection_rank"),
                "film_title": film.get("title"),
                "film_year": film.get("year"),
                "wikipedia_url": film.get("wikipedia_attribution_url"),
                "wikipedia_revision": film.get("wikipedia_revision"),
                "wikipedia_snapshot_sha256": film.get("wikipedia_sha256"),
                "wikipedia_license": film.get("wikipedia_license"),
            })
        for ambiguity in result["ambiguities"]:
            ambiguity_rows.append({
                **ambiguity,
                "selection_rank": film.get("selection_rank"),
                "film_title": film.get("title"),
                "wikipedia_url": film.get("wikipedia_attribution_url"),
                "wikipedia_revision": film.get("wikipedia_revision"),
                "wikipedia_snapshot_sha256": film.get("wikipedia_sha256"),
            })
        film_rows.append({
            "selection_rank": film.get("selection_rank"), "film_qid": qid,
            "title": film.get("title"), "year": film.get("year"),
            "cast_passages": result["cast_passage_count"],
            "candidate_count": len(identity_candidates),
            "ambiguous_or_unmatched_count": len(result["ambiguities"]),
            "source_revision": film.get("wikipedia_revision"),
            "source_sha256": film.get("wikipedia_sha256"),
        })

    candidate_rows.sort(key=lambda row: (
        row["selection_rank"], row["actor_label_in_source"].casefold(),
        row["character_name_in_source"].casefold(), row["section_locator"],
        row["passage_ordinal"],
    ))
    return {
        "schema": "cinegraph.wikipedia-cast-candidates/v8",
        "adapter_version": ADAPTER_VERSION,
        "selection_sha256": capture_manifest["selection_sha256"],
        "film_capture_manifest_sha256": hashlib.sha256(capture_bytes).hexdigest(),
        "credit_target_manifest_sha256": hashlib.sha256(credit_bytes).hexdigest(),
        "credit_label_checkpoint_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
        "passage_extraction_manifest_sha256": hashlib.sha256(extraction_bytes).hexdigest() if extraction_bytes else None,
        "source_license_note": "Wikipedia text is attributed CC BY-SA 4.0 source material; assess each use separately.",
        "operational_fact_write": False,
        "summary": {
            "films": len(film_rows),
            "films_with_cast_passages": sum(row["cast_passages"] > 0 for row in film_rows),
            "films_with_candidates": sum(row["candidate_count"] > 0 for row in film_rows),
            "candidate_rows": len(candidate_rows),
            "ambiguous_or_unmatched_rows": len(ambiguity_rows),
            "wikidata_actor_candidates": sum(row["actor_qid"] is not None for row in candidate_rows),
            "source_only_identity_matches": sum(
                row.get("actor_identity_qid") is not None and row.get("actor_qid") is None
                for row in candidate_rows
            ),
            "source_only_exact_label_matches": sum(
                row.get("actor_qid") is None
                and row.get("actor_identity_match") == "exact_unique_english_label"
                for row in candidate_rows
            ),
            "source_only_exact_alias_matches": sum(
                row.get("actor_qid") is None
                and row.get("actor_identity_match") == "exact_unique_english_alias"
                for row in candidate_rows
            ),
            "ambiguous_source_identity_candidates": sum(
                row.get("identity_resolution") == "ambiguous_captured_person_identity"
                for row in candidate_rows
            ),
            "source_only_unresolved_candidates": sum(
                row.get("identity_resolution") == "unresolved_source_name" for row in candidate_rows
            ),
            "candidates_matching_wikidata_character_label": sum(
                bool(row["matching_wikidata_character_qids"]) for row in candidate_rows
            ),
        },
        "films": film_rows,
        "candidates": candidate_rows,
        "ambiguities": ambiguity_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Retained English 100-film capture bundle")
    parser.add_argument("credit_manifest", type=Path, help="Audited credit-target manifest JSON")
    parser.add_argument("credit_label_dir", type=Path, help="Complete local Wikidata label capture directory")
    parser.add_argument("output", type=Path, help="New ignored local JSON report path; existing files are not overwritten")
    parser.add_argument("--extraction-manifest", type=Path,
                        help="Versioned passage extraction manifest to bind against the captured revisions")
    args = parser.parse_args()
    result = prepare(args.bundle, args.credit_manifest, args.credit_label_dir, args.extraction_manifest)
    payload = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    _write_immutable(args.output, payload)
    print(json.dumps(result["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
