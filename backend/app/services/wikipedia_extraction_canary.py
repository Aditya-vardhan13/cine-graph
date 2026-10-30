"""Read-only ten-film comparison of retained Wikipedia extraction versions.

Run in an ephemeral local container that can read the raw-snapshot volume and
connect only to ``cinegraph_eval``. The report contains counts, not article
text; source snapshots and existing narrative passages are never changed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from app.models import CanonicalEntity, NarrativePassage, SourceSnapshot
from app.services.wikipedia_research import (
    _snapshot_payload, chunk_section, clean_wikitext, snapshot_wikitext, split_sections,
)
from app.services.wikipedia_text_v2 import EXTRACTION_VERSION, chunk_section_v2, readable_wikitext


_PRESENTATION_MARKER = re.compile(r"thumb\||alt=|\[\[|\{\{", re.IGNORECASE)


def compare_revision(payload: dict) -> dict:
    """Compare identical section/paragraph units without selecting good-looking cases."""
    wikitext, _, _ = snapshot_wikitext(payload)
    report = {
        "sections": 0,
        "legacy_passages": 0,
        "passages": 0,
        "old_marker_passages": 0,
        "new_marker_passages": 0,
        "old_characters": 0,
        "new_characters": 0,
        "large_text_reductions": 0,
        "removed_media": 0,
        "media_caption_characters": 0,
        "removed_citations": 0,
        "diagnostics": [],
    }
    for section in split_sections(wikitext):
        report["sections"] += 1
        report["legacy_passages"] += len(list(chunk_section(str(section["content"]))))
        for ordinal, raw in enumerate(chunk_section_v2(str(section["content"]))):
            old_text = clean_wikitext(raw)
            parsed = readable_wikitext(raw)
            old_marker = bool(_PRESENTATION_MARKER.search(old_text))
            new_marker = bool(_PRESENTATION_MARKER.search(parsed.text))
            large_reduction = bool(old_text and len(parsed.text) < 0.5 * len(old_text))
            report["passages"] += 1
            report["old_marker_passages"] += old_marker
            report["new_marker_passages"] += new_marker
            report["old_characters"] += len(old_text)
            report["new_characters"] += len(parsed.text)
            report["large_text_reductions"] += large_reduction
            report["removed_media"] += len(parsed.removed_media)
            report["media_caption_characters"] += sum(len(caption) for caption in parsed.media_captions)
            report["removed_citations"] += len(parsed.removed_citations)
            if new_marker or large_reduction:
                marker = _PRESENTATION_MARKER.search(parsed.text)
                report["diagnostics"].append({
                    "section_locator": section["locator"],
                    "ordinal": ordinal,
                    "new_marker": new_marker,
                    "large_reduction": large_reduction,
                    "old_excerpt": old_text[:180],
                    "new_excerpt": parsed.text[:180],
                    "marker_excerpt": (
                        parsed.text[max(0, marker.start() - 60):marker.end() + 60]
                        if marker else None
                    ),
                    "media_captions": parsed.media_captions,
                })
    return report


def run_canary(db: Session, qids: list[str]) -> dict:
    if len(qids) != 10 or len(set(qids)) != 10:
        raise ValueError("The extraction canary requires exactly ten distinct films.")
    rows = db.execute(
        select(CanonicalEntity.wikidata_id, SourceSnapshot)
        .join(NarrativePassage, NarrativePassage.subject_entity_id == CanonicalEntity.id)
        .join(SourceSnapshot, SourceSnapshot.id == NarrativePassage.source_snapshot_id)
        .where(CanonicalEntity.wikidata_id.in_(qids), SourceSnapshot.fetch_status == "success")
        .order_by(CanonicalEntity.wikidata_id, SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc())
        .distinct(CanonicalEntity.wikidata_id)
    ).all()
    by_qid = {qid: snapshot for qid, snapshot in rows}
    if set(by_qid) != set(qids):
        raise ValueError(f"Missing retained revisions for {sorted(set(qids) - set(by_qid))}")
    films = []
    for qid in qids:
        snapshot = by_qid[qid]
        if snapshot.license != "CC BY-SA 4.0" or not snapshot.attribution_url:
            raise ValueError(f"Snapshot {snapshot.id} lacks required attribution.")
        film_report = compare_revision(_snapshot_payload(snapshot))
        films.append({
            "qid": qid,
            "snapshot_id": str(snapshot.id),
            "source_revision": snapshot.source_revision,
            **film_report,
        })
    totals = {
        key: sum(film[key] for film in films)
        for key in ("sections", "legacy_passages", "passages", "old_marker_passages", "new_marker_passages",
                    "old_characters", "new_characters", "large_text_reductions",
                    "removed_media", "media_caption_characters", "removed_citations")
    }
    return {
        "extraction_version": EXTRACTION_VERSION,
        "film_count": len(films),
        "totals": totals,
        "films": films,
        "caution": "Marker reduction alone is not evidence retention; inspect large text reductions before migration.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if make_url(args.database_url).database != "cinegraph_eval":
        raise ValueError("The extraction canary may run only against cinegraph_eval.")
    report_root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    output_path = args.output.resolve()
    if not output_path.is_relative_to(report_root):
        raise ValueError("The report must stay under ignored project-local data/evaluation.")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    qids = [qid for pair in manifest["pairs"][:5] for qid in pair["films"]]
    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            report = run_canary(db, qids)
    finally:
        engine.dispose()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"film_count": report["film_count"], "totals": report["totals"]}, indent=2))


if __name__ == "__main__":
    main()
