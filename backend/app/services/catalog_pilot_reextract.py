"""Create and verify a new parser-version derivative from retained pilot bytes."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from app.services.wikipedia_article_html import PARSER_VERSION, parse_article_html


class CatalogPilotExtractionError(RuntimeError):
    """A retained source or immutable extraction derivative failed validation."""


def validate_citation_positions(passage: Any) -> None:
    """Reject locators outside their declared paragraph; this does not prove support."""
    paragraphs = passage.content.split("\n\n")
    starts: list[int] = []
    offset = 0
    for paragraph in paragraphs:
        starts.append(offset)
        offset += len(paragraph) + 2
    markers = set(passage.citation_markers)
    if markers != {marker for marker, _, _ in passage.citation_positions}:
        raise CatalogPilotExtractionError("citation marker and position sets differ")
    for marker, paragraph_index, char_offset in passage.citation_positions:
        if not isinstance(paragraph_index, int) or not isinstance(char_offset, int):
            raise CatalogPilotExtractionError("citation position must use integer coordinates")
        if not 0 <= paragraph_index < len(paragraphs):
            raise CatalogPilotExtractionError("citation paragraph index is out of bounds")
        start = starts[paragraph_index]
        if not start <= char_offset <= start + len(paragraphs[paragraph_index]):
            raise CatalogPilotExtractionError("citation offset is outside its paragraph")


def _write_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise CatalogPilotExtractionError(f"Refusing to overwrite immutable derivative: {path}")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _passage_payload(document: Any, source_sha256: str) -> bytes:
    version_suffix = PARSER_VERSION.rsplit("-v", 1)[-1]
    value = {
        "schema": f"cinegraph.wikipedia-passage-extraction/v{version_suffix}",
        "source_snapshot_sha256": source_sha256,
        "source_revision": document.metadata.revision_id,
        "parser_version": document.parser_version,
        "passages": [
            {
                "section_locator": passage.section_locator,
                "section_title": passage.section_title,
                "ordinal": passage.ordinal,
                "content": passage.content,
                "citation_markers": list(passage.citation_markers),
                "citation_positions": [
                    {"marker_id": marker, "paragraph_index": paragraph_index,
                     "char_offset": char_offset}
                    for marker, paragraph_index, char_offset in passage.citation_positions
                ],
                "content_sha256": passage.content_hash,
            }
            for passage in document.passages
        ],
    }
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def derive_catalog_pilot(bundle: Path) -> dict[str, Any]:
    """Re-extract every captured title without network or source mutation.

    The original capture manifest and prior passage derivatives are not
    rewritten. New, content-addressed parser-version derivatives and a distinct
    manifest are created beside them.
    """
    bundle = bundle.resolve()
    capture = json.loads((bundle / "capture-manifest.json").read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for film in capture.get("films", []):
        if film.get("capture_status") != "complete" or film.get("wikipedia_status") != "captured":
            raise CatalogPilotExtractionError(f"Pilot capture is not complete for {film.get('qid')}.")
        source_path = bundle / film["wikipedia_snapshot_path"]
        source_bytes = source_path.read_bytes()
        source_hash = sha256(source_bytes).hexdigest()
        if source_hash != film.get("wikipedia_sha256"):
            raise CatalogPilotExtractionError(f"Retained article hash mismatch for {film['qid']}.")
        document = parse_article_html(
            source_bytes, canonical_url=film["wikipedia_capture_url"], expected_qid=film["qid"],
        )
        if (document.metadata.revision_id != film.get("wikipedia_revision")
                or document.metadata.title != film.get("wikipedia_title_resolved")):
            raise CatalogPilotExtractionError(f"Article identity/revision mismatch for {film['qid']}.")
        payload = _passage_payload(document, source_hash)
        derivative_hash = sha256(payload).hexdigest()
        version_suffix = PARSER_VERSION.rsplit("-v", 1)[-1]
        relative_derivative = (
            Path("snapshots") / f"wikipedia-passages-v{version_suffix}"
            / film["qid"] / f"{derivative_hash}.json"
        )
        _write_immutable(bundle / relative_derivative, payload)
        rows.append({
            "qid": film["qid"],
            "title": film["title"],
            "year": film["year"],
            "canonical_url": film["wikipedia_capture_url"],
            "source_snapshot_path": film["wikipedia_snapshot_path"],
            "source_snapshot_sha256": source_hash,
            "source_revision": document.metadata.revision_id,
            "parser_version": document.parser_version,
            "passage_derivative_path": relative_derivative.as_posix(),
            "passage_derivative_sha256": derivative_hash,
            "passage_count": len(document.passages),
            "citation_marker_occurrences": sum(len(passage.citation_positions) for passage in document.passages),
        })
    manifest = {
        "schema": "cinegraph.catalog-pilot-extraction/v1",
        "selection_sha256": capture.get("selection_sha256"),
        "parser_version": PARSER_VERSION,
        "films": rows,
    }
    manifest_payload = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    version_suffix = PARSER_VERSION.rsplit("-v", 1)[-1]
    _write_immutable(bundle / f"extraction-manifest-{version_suffix}.json", manifest_payload)
    return manifest


def audit_catalog_pilot_extraction(bundle: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Reparse retained bytes and prove a versioned derivative is exact."""
    bundle = bundle.resolve()
    films: list[dict[str, Any]] = []
    total_passages = 0
    total_markers = 0
    total_duplicates = 0
    all_text_hashes: Counter[str] = Counter()
    errors: list[str] = []
    if manifest.get("parser_version") != PARSER_VERSION:
        raise CatalogPilotExtractionError("Extraction manifest parser version differs from this audit implementation.")
    for film in manifest.get("films", []):
        try:
            source = (bundle / film["source_snapshot_path"]).read_bytes()
            if sha256(source).hexdigest() != film["source_snapshot_sha256"]:
                raise CatalogPilotExtractionError("source snapshot hash mismatch")
            document = parse_article_html(
                source, canonical_url=film["canonical_url"],
                expected_qid=film["qid"],
            )
            if document.metadata.revision_id != film["source_revision"]:
                raise CatalogPilotExtractionError("source revision mismatch")
            derivative_bytes = (bundle / film["passage_derivative_path"]).read_bytes()
            if sha256(derivative_bytes).hexdigest() != film["passage_derivative_sha256"]:
                raise CatalogPilotExtractionError("passage derivative hash mismatch")
            derivative = json.loads(derivative_bytes)
            expected = json.loads(_passage_payload(document, film["source_snapshot_sha256"]))
            if derivative != expected or len(document.passages) != film["passage_count"]:
                raise CatalogPilotExtractionError("passage derivative differs from deterministic parser output")
            markers = sum(len(passage.citation_positions) for passage in document.passages)
            if markers != film["citation_marker_occurrences"]:
                raise CatalogPilotExtractionError("citation marker count mismatch")
            for passage in document.passages:
                validate_citation_positions(passage)
                all_text_hashes[passage.content_hash] += 1
            total_passages += len(document.passages)
            total_markers += markers
            films.append({"qid": film["qid"], "title": film["title"],
                          "passages": len(document.passages), "citation_markers": markers,
                          "source_revision": document.metadata.revision_id})
        except (KeyError, OSError, ValueError, TypeError, CatalogPilotExtractionError) as exc:
            errors.append(f"{film.get('title')} ({film.get('qid')}): {type(exc).__name__}: {exc}")
    total_duplicates = sum(count - 1 for count in all_text_hashes.values() if count > 1)
    return {
        "schema": "cinegraph.catalog-pilot-extraction-audit/v1",
        "parser_version": manifest.get("parser_version"),
        "selection_sha256": manifest.get("selection_sha256"),
        "audited_films": len(films),
        "requested_films": len(manifest.get("films", [])),
        "pass": not errors and len(films) == len(manifest.get("films", [])),
        "total_passages": total_passages,
        "citation_marker_occurrences": total_markers,
        "exact_duplicate_passages": total_duplicates,
        "failures": errors,
        "films": films,
    }
