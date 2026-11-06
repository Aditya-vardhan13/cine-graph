"""Cross-check extracted Wikipedia cast phrases against exact Wikidata P453 claims."""
from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Any
from urllib.parse import urlparse

from app.services.credit_target_manifest import snak_qid
from app.services.wikidata_raw import entity_from_entitydata


_QID = re.compile(r"^Q[1-9][0-9]*$")
_STATEMENT = re.compile(r"^claims\.P161\[(\d+)\]$")
_QUALIFIER = re.compile(r"^qualifiers\.P453\[(\d+)\]$")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _label_key(value: Any) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold() if isinstance(value, str) else ""


def _captured_claim(entity: dict[str, Any], statement_locator: str, qualifier_locator: str) -> tuple[dict, str, str]:
    statement_match = _STATEMENT.fullmatch(statement_locator)
    qualifier_match = _QUALIFIER.fullmatch(qualifier_locator)
    if statement_match is None or qualifier_match is None:
        raise ValueError("Cast character link has a malformed P161/P453 locator")
    claims = entity.get("claims", {})
    cast = claims.get("P161", []) if isinstance(claims, dict) else []
    statement_index = int(statement_match.group(1))
    qualifier_index = int(qualifier_match.group(1))
    if not isinstance(cast, list) or statement_index >= len(cast):
        raise ValueError("Cast statement locator is outside the retained Wikidata entity")
    statement = cast[statement_index]
    if not isinstance(statement, dict) or statement.get("rank") == "deprecated":
        raise ValueError("Wikidata cast statement is missing or deprecated")
    actor_qid = snak_qid(statement.get("mainsnak"))
    qualifiers = statement.get("qualifiers", {})
    character_snaks = qualifiers.get("P453", []) if isinstance(qualifiers, dict) else []
    if not isinstance(character_snaks, list) or qualifier_index >= len(character_snaks):
        raise ValueError("Character qualifier locator is outside the retained Wikidata statement")
    character_qid = snak_qid(character_snaks[qualifier_index])
    if not actor_qid or not character_qid:
        raise ValueError("Wikidata P161/P453 statement does not contain entity QIDs")
    return statement, actor_qid, character_qid


def _passage_lookup(payload: dict[str, Any], payload_bytes: bytes,
                    source_film: dict[str, Any], binding: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    if _sha256(payload_bytes) != binding.get("passage_derivative_sha256"):
        raise ValueError("Wikipedia passage derivative checksum mismatch")
    if (payload.get("schema") not in {
            "cinegraph.wikipedia-passage-extraction/v6",
            "cinegraph.wikipedia-passage-extraction/6",
        }
            or payload.get("parser_version") != binding.get("parser_version")
            or binding.get("parser_version") != "enwiki-article-html-extraction-v6"
            or payload.get("source_revision") != source_film.get("wikipedia_revision")
            or payload.get("source_snapshot_sha256") != source_film.get("wikipedia_sha256")):
        raise ValueError("Wikipedia passage derivative is not bound to the retained article revision")
    passages = payload.get("passages")
    if not isinstance(passages, list):
        raise ValueError("Wikipedia passage derivative has no passage list")
    lookup: dict[tuple[str, int], dict[str, Any]] = {}
    for passage in passages:
        if not isinstance(passage, dict):
            raise ValueError("Malformed passage derivative row")
        locator, ordinal, content = passage.get("section_locator"), passage.get("ordinal"), passage.get("content")
        if (not isinstance(locator, str) or not isinstance(ordinal, int) or isinstance(ordinal, bool)
                or not isinstance(content, str)):
            raise ValueError("Passage derivative row has malformed locator, ordinal or content")
        digest = _sha256(content.encode("utf-8"))
        if passage.get("content_sha256") != digest:
            raise ValueError("Passage content checksum differs from retained derivative")
        key = (locator, ordinal)
        if key in lookup:
            raise ValueError("Passage derivative repeats a section locator and ordinal")
        lookup[key] = passage
    return lookup


def _validate_candidate_passage(row: dict[str, Any], passages: dict[tuple[str, int], dict[str, Any]]) -> None:
    key = (row.get("section_locator"), row.get("passage_ordinal"))
    passage = passages.get(key)
    if passage is None:
        raise ValueError("Candidate refers to a missing retained passage")
    content = passage["content"]
    phrase = row.get("evidence_phrase")
    character_name = row.get("character_name_in_source")
    if (_sha256(content.encode("utf-8")) != row.get("passage_sha256")
            or not isinstance(phrase, str) or not phrase or phrase not in content
            or not isinstance(character_name, str) or not character_name.strip()
            or character_name not in phrase):
        raise ValueError("Candidate evidence phrase/character name is not present in its retained passage")


def build_wikidata_cast_character_crosswalk(
    partitions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify candidate-aligned P453 links against retained film snapshots.

    Each partition contains exact candidate/capture/target/checkpoint bytes,
    parsed manifests, and raw Wikidata entity payloads keyed by film QID. This
    produces a supplementary cross-source audit only; it writes no assertions.
    """
    if not partitions:
        raise ValueError("At least one retained pilot partition is required")

    films: dict[int, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    partition_hashes: list[dict[str, str]] = []
    all_selection_ranks: set[int] = set()

    for part in partitions:
        candidate_report = part.get("candidate_report")
        capture = part.get("capture_manifest")
        targets = part.get("credit_target_manifest")
        checkpoint = part.get("label_checkpoint")
        raw = part.get("raw_bytes")
        snapshots = part.get("film_snapshots")
        passage_snapshots = part.get("passage_snapshots")
        passage_bindings = part.get("passage_derivative_bindings")
        if not all(isinstance(value, dict) for value in (
                candidate_report, capture, targets, checkpoint, raw, snapshots, passage_snapshots,
                passage_bindings)):
            raise ValueError("Partition is missing one of its retained inputs")
        for key, schema in (
            ("candidate_report", "cinegraph.wikipedia-cast-candidates/v7"),
            ("capture_manifest", "cinegraph.catalog-pilot-capture/v1"),
            ("credit_target_manifest", "cinegraph.credit-target-manifest/v1"),
        ):
            if part[key].get("schema") != schema:
                raise ValueError(f"Unexpected {key} schema")
        candidate_sha = _sha256(raw["candidate_report"])
        capture_sha = _sha256(raw["capture_manifest"])
        targets_sha = _sha256(raw["credit_target_manifest"])
        checkpoint_sha = _sha256(raw["label_checkpoint"])
        if candidate_report.get("film_capture_manifest_sha256") != capture_sha:
            raise ValueError("Candidate report does not bind to this exact capture manifest")
        if candidate_report.get("credit_target_manifest_sha256") != targets_sha:
            raise ValueError("Candidate report does not bind to this exact credit-target manifest")
        if candidate_report.get("credit_label_checkpoint_sha256") != checkpoint_sha:
            raise ValueError("Candidate report does not bind to this exact credit-label checkpoint")
        selection = candidate_report.get("selection_sha256")
        if (not isinstance(selection, str)
                or capture.get("selection_sha256") != selection
                or targets.get("selection_sha256") != selection
                or checkpoint.get("manifest_sha256") != targets_sha):
            raise ValueError("Candidate, capture, targets and label checkpoint selections differ")
        partition_hashes.append({
            "selection_sha256": selection,
            "candidate_report_sha256": candidate_sha,
            "capture_manifest_sha256": capture_sha,
            "credit_target_manifest_sha256": targets_sha,
            "label_checkpoint_sha256": checkpoint_sha,
        })

        capture_films = capture.get("films")
        candidate_films = candidate_report.get("films")
        candidates = candidate_report.get("candidates")
        target_rows = targets.get("targets")
        captured_labels = checkpoint.get("captured")
        if not all(isinstance(value, list) for value in (capture_films, candidate_films, candidates, target_rows)):
            raise ValueError("A partition input is missing its film, candidate or target rows")
        if not isinstance(captured_labels, dict) or not isinstance(snapshots, dict):
            raise ValueError("A partition input is missing captured labels or film snapshots")
        capture_by_qid = {film.get("qid"): film for film in capture_films if isinstance(film, dict)}
        target_by_character: dict[str, list[dict[str, Any]]] = {}
        for target in target_rows:
            if not isinstance(target, dict) or not isinstance(target.get("qid"), str):
                raise ValueError("Malformed credit target row")
            for reference in target.get("references", []):
                if not isinstance(reference, dict) or reference.get("role") != "character":
                    continue
                film_reference = reference.get("film_qid")
                if not isinstance(film_reference, str) or not _QID.fullmatch(film_reference):
                    raise ValueError("Character target has an invalid film QID")
                target_by_character.setdefault(film_reference, []).append({
                    **reference,
                    "character_qid": target["qid"],
                })

        candidate_film_rows: dict[str, dict[str, Any]] = {}
        passage_lookups: dict[str, dict[tuple[str, int], dict[str, Any]]] = {}
        for film in candidate_films:
            if not isinstance(film, dict):
                raise ValueError("Malformed candidate film row")
            qid = film.get("film_qid")
            source_film = capture_by_qid.get(qid)
            if source_film is None:
                raise ValueError("Candidate film is absent from its captured source manifest")
            rank = film.get("selection_rank")
            if not isinstance(rank, int) or isinstance(rank, bool) or rank in all_selection_ranks:
                raise ValueError("Candidate partitions repeat a pilot rank")
            all_selection_ranks.add(rank)
            if (film.get("source_revision") != source_film.get("wikipedia_revision")
                    or film.get("source_sha256") != source_film.get("wikipedia_sha256")
                    or film.get("title") != source_film.get("title")
                    or film.get("year") != source_film.get("year")):
                raise ValueError("Candidate film does not match its retained Wikipedia capture")
            entity, payload = snapshots.get(qid, (None, None))
            if not isinstance(entity, dict) or not isinstance(payload, bytes):
                raise ValueError(f"Missing retained Wikidata snapshot for {qid}")
            if _sha256(payload) != source_film.get("wikidata_sha256"):
                raise ValueError(f"Wikidata snapshot checksum mismatch for {qid}")
            entity_root = entity.get("entities", {})
            wikidata_film = entity_root.get(qid, {}) if isinstance(entity_root, dict) else {}
            if (wikidata_film.get("id") != qid
                    or str(wikidata_film.get("lastrevid")) != str(source_film.get("wikidata_revision"))):
                raise ValueError(f"Wikidata snapshot identity/revision mismatch for {qid}")
            candidate_film_rows[qid] = film
            passage_payload, passage_bytes = passage_snapshots.get(qid, (None, None))
            if not isinstance(passage_payload, dict) or not isinstance(passage_bytes, bytes):
                raise ValueError(f"Missing retained Wikipedia passage derivative for {qid}")
            binding = passage_bindings.get(qid)
            if not isinstance(binding, dict):
                raise ValueError(f"Missing passage derivative binding for {qid}")
            passage_lookups[qid] = _passage_lookup(passage_payload, passage_bytes, source_film, binding)
            existing = films.get(rank)
            if existing is not None:
                raise ValueError("Pilot ranks must be unique across candidate partitions")
            films[rank] = {
                "selection_rank": rank,
                "film_qid": qid,
                "title": film.get("title"),
                "year": film.get("year"),
                "wikipedia_revision": film.get("source_revision"),
                "wikidata_revision": source_film.get("wikidata_revision"),
                "wikidata_snapshot_sha256": source_film.get("wikidata_sha256"),
                "candidate_count": 0,
                "candidates_with_direct_p453_link": 0,
                "exact_character_label_agreements": 0,
                "direct_p453_links": 0,
            }

        for row in candidates:
            if not isinstance(row, dict):
                raise ValueError("Candidate row must be an object")
            film_qid = row.get("film_qid")
            if film_qid not in passage_lookups:
                raise ValueError("Candidate row points outside its retained film partitions")
            source_url = row.get("wikipedia_url")
            parsed_url = urlparse(source_url) if isinstance(source_url, str) else None
            if (parsed_url is None or parsed_url.scheme != "https"
                    or parsed_url.hostname != "en.wikipedia.org"
                    or not parsed_url.path.startswith("/wiki/")
                    or source_url != capture_by_qid[film_qid].get("wikipedia_attribution_url")):
                raise ValueError("Candidate Wikipedia URL differs from its retained canonical article URL")
            _validate_candidate_passage(row, passage_lookups[film_qid])
            if row.get("identity_resolution") != "same_film_wikidata_cast_target":
                continue
            actor_qid = row.get("actor_qid")
            film = candidate_film_rows.get(film_qid)
            if film is None or not isinstance(actor_qid, str) or not _QID.fullmatch(actor_qid):
                raise ValueError("Same-film candidate has invalid film or person identity")
            if row.get("review_status") != "review_required":
                raise ValueError("Source candidate must remain review_required")
            captured_film = capture_by_qid[film_qid]
            actor_locators = row.get("actor_statement_locators")
            if not isinstance(actor_locators, list) or any(not isinstance(value, str) for value in actor_locators):
                raise ValueError("Candidate lacks its exact Wikidata cast statement locators")
            entity, _ = snapshots[film_qid]
            wikidata_film = entity["entities"][film_qid]
            matching_links: list[dict[str, Any]] = []
            for reference in target_by_character.get(film_qid, []):
                if reference.get("person_qid") != actor_qid:
                    continue
                if reference.get("source_revision") != captured_film.get("wikidata_revision"):
                    raise ValueError("Character target revision differs from captured film entity")
                if reference.get("source_sha256") != captured_film.get("wikidata_sha256"):
                    raise ValueError("Character target hash differs from captured film entity")
                statement_locator = reference.get("statement_locator")
                if statement_locator not in actor_locators:
                    continue
                statement, claimed_actor_qid, claimed_character_qid = _captured_claim(
                    wikidata_film, statement_locator, reference.get("qualifier_locator", ""),
                )
                if claimed_actor_qid != actor_qid or claimed_character_qid != reference.get("character_qid"):
                    raise ValueError("Retained Wikidata P161/P453 values disagree with target manifest")
                captured_label = captured_labels.get(reference["character_qid"])
                if not isinstance(captured_label, dict):
                    raise ValueError("Directly linked character has no captured label record")
                character_label = captured_label.get("english_label")
                if not isinstance(character_label, str) or not character_label.strip():
                    continue
                label_payload = (part.get("label_snapshot_payloads") or {}).get(reference["character_qid"])
                if not isinstance(label_payload, bytes) or _sha256(label_payload) != captured_label.get("sha256"):
                    raise ValueError("Captured character-label snapshot checksum mismatch")
                label_entity = entity_from_entitydata(json.loads(label_payload), reference["character_qid"])
                if (str(label_entity.get("lastrevid")) != str(captured_label.get("source_revision"))
                        or label_entity.get("labels", {}).get("en", {}).get("value") != character_label):
                    raise ValueError("Captured character label differs from its exact Wikidata snapshot")
                agreement = _label_key(row.get("character_name_in_source")) == _label_key(character_label)
                matching_links.append({
                    "actor_qid": actor_qid,
                    "actor_label": row.get("actor_label"),
                    "character_qid": reference["character_qid"],
                    "character_label": character_label,
                    "source_text_character": row.get("character_name_in_source"),
                    "exact_text_label_agreement": agreement,
                    "cast_statement_locator": statement_locator,
                    "character_qualifier_locator": reference["qualifier_locator"],
                    "wikidata_film_revision": captured_film["wikidata_revision"],
                    "wikidata_film_snapshot_sha256": captured_film["wikidata_sha256"],
                    "wikidata_statement_rank": statement.get("rank"),
                    "wikidata_statement_reference_count": len(statement.get("references", [])),
                    "wikipedia_revision": row.get("wikipedia_revision"),
                    "wikipedia_snapshot_sha256": row.get("wikipedia_snapshot_sha256"),
                    "wikipedia_url": row.get("wikipedia_url"),
                    "wikipedia_section_locator": row.get("section_locator"),
                    "wikipedia_passage_sha256": row.get("passage_sha256"),
                    "review_status": "review_required",
                })
            film_report = films[film.get("selection_rank")]
            film_report["candidate_count"] += 1
            if matching_links:
                film_report["candidates_with_direct_p453_link"] += 1
                film_report["direct_p453_links"] += len(matching_links)
                if any(link["exact_text_label_agreement"] for link in matching_links):
                    film_report["exact_character_label_agreements"] += 1
                links.extend({"selection_rank": film_report["selection_rank"],
                              "film_qid": film_qid, "film_title": film.get("title"),
                              **link} for link in matching_links)

    links.sort(key=lambda row: (row["selection_rank"], row["actor_qid"], row["character_qid"], row["cast_statement_locator"]))
    summary = {
        "films": len(films),
        "same_film_actor_candidates": sum(film["candidate_count"] for film in films.values()),
        "candidates_with_direct_p453_link": sum(film["candidates_with_direct_p453_link"] for film in films.values()),
        "direct_p453_links": sum(film["direct_p453_links"] for film in films.values()),
        "exact_character_label_agreements": sum(film["exact_character_label_agreements"] for film in films.values()),
        "review_required": len(links),
        "operational_assertions_written": False,
    }
    return {
        "schema": "cinegraph.wikidata-cast-character-crosswalk/v1",
        "partitions": partition_hashes,
        "summary": summary,
        "films": [films[rank] for rank in sorted(films)],
        "direct_links": links,
        "limitations": [
            "P453 links are Wikidata source statements, not human-approved operational assertions.",
            "Exact English label agreement does not prove that the Wikipedia passage and Wikidata claim have identical scope.",
            "Only directly linked characters with a captured English label are included.",
        ],
    }


def render_wikidata_cast_character_crosswalk(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Cross-source actor–character evidence — English pilot",
        "",
        "> These rows join an explicit Wikipedia `Actor as Character` passage to a P453 qualifier on the exact Wikidata P161 cast statement. They remain review candidates, not published credits.",
        "",
        f"- Films checked: **{summary['films']}**",
        f"- Same-film actor candidates: **{summary['same_film_actor_candidates']}**",
        f"- Candidates with direct P453 links: **{summary['candidates_with_direct_p453_link']}**",
        f"- Direct actor–character statement links: **{summary['direct_p453_links']}**",
        f"- Exact English character-label agreements with extracted Wikipedia role names: **{summary['exact_character_label_agreements']}**",
        "",
        "| Rank | Film | Actor | Wikipedia role text | Wikidata character | Exact label | P161 / P453 locator | Wikidata revision | Wikidata refs | Wikipedia revision |",
        "|---:|---|---|---|---|:---:|---|---:|---:|---:|",
    ]
    for row in report["direct_links"]:
        wiki_url = f"{row['wikipedia_url']}?oldid={row['wikipedia_revision']}"
        wd_url = f"https://www.wikidata.org/wiki/{row['film_qid']}?oldid={row['wikidata_film_revision']}"
        lines.append(
            f"| {row['selection_rank']} | {row['film_title']} | {row['actor_label']} (`{row['actor_qid']}`) | "
            f"{row['source_text_character']} | {row['character_label']} (`{row['character_qid']}`) | "
            f"{'yes' if row['exact_text_label_agreement'] else 'no'} | `{row['cast_statement_locator']}` / `{row['character_qualifier_locator']}` | "
            f"[{row['wikidata_film_revision']}]({wd_url}) | {row['wikidata_statement_reference_count']} | "
            f"[{row['wikipedia_revision']}]({wiki_url}) |"
        )
    lines.extend([
        "",
        "## Source manifest fingerprints",
        "",
    ])
    for partition in report["partitions"]:
        lines.append(
            f"- Selection `{partition['selection_sha256']}`; candidate `{partition['candidate_report_sha256']}`; "
            f"capture `{partition['capture_manifest_sha256']}`; target `{partition['credit_target_manifest_sha256']}`; "
            f"label checkpoint `{partition['label_checkpoint_sha256']}`."
        )
    lines.extend(["", *[f"- Limitation: {item}" for item in report["limitations"]], ""])
    return "\n".join(lines)


def render_wikidata_cast_character_review_html(report: dict[str, Any]) -> str:
    """Render a self-contained, filterable human review page without source prose."""
    summary = report["summary"]
    films = report["films"]
    options = "".join(
        f'<option value="{html.escape(str(film["title"]), quote=True)}">'
        f'{html.escape(str(film["selection_rank"]))} · {html.escape(str(film["title"]))}</option>'
        for film in films
    )
    rows: list[str] = []
    for row in report["direct_links"]:
        safe = lambda value: html.escape(str(value), quote=True)
        film_url = f"https://www.wikidata.org/wiki/{row['film_qid']}?oldid={row['wikidata_film_revision']}"
        wikipedia_url = f"{row['wikipedia_url']}?oldid={row['wikipedia_revision']}"
        agreement = "yes" if row["exact_text_label_agreement"] else "no"
        search = " ".join(str(row.get(key, "")) for key in (
            "film_title", "actor_label", "actor_qid", "source_text_character",
            "character_label", "character_qid",
        )).casefold()
        rows.append(
            f'<tr data-film="{safe(row["film_title"])}" data-agreement="{agreement}" '
            f'data-search="{safe(search)}"><td>{safe(row["selection_rank"])} · {safe(row["film_title"])}</td>'
            f'<td>{safe(row["actor_label"])} <small>{safe(row["actor_qid"])}</small></td>'
            f'<td>{safe(row["source_text_character"])}</td>'
            f'<td>{safe(row["character_label"])} <small>{safe(row["character_qid"])}</small></td>'
            f'<td><span class="badge {agreement}">{agreement}</span></td>'
            f'<td><a href="{safe(film_url)}" target="_blank" rel="noopener noreferrer">Wikidata r{safe(row["wikidata_film_revision"])} ↗</a>'
            f'<br><a href="{safe(wikipedia_url)}" target="_blank" rel="noopener noreferrer">Wikipedia r{safe(row["wikipedia_revision"])} ↗</a>'
            f'<small class="locator">{safe(row["cast_statement_locator"])} / {safe(row["character_qualifier_locator"])}</small></td>'
            f'<td>{safe(row["wikidata_statement_reference_count"])}</td></tr>'
        )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CineGraph · Cast-character evidence review</title>
<style>
:root{color-scheme:dark;--bg:#0b1018;--panel:#121c29;--line:#2a394b;--text:#e8eef7;--muted:#a6b4c5;--accent:#87e3cc}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 15% 0,#193248 0,transparent 44%),var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif}
main{max-width:1500px;margin:auto;padding:32px 24px}h1{margin:4px 0 8px;font-size:clamp(26px,4vw,40px)}p{color:var(--muted)}.kicker{color:var(--accent);font-size:12px;letter-spacing:.14em;text-transform:uppercase}
.stats,.filters{display:flex;flex-wrap:wrap;gap:12px;margin:22px 0}.stat,.filters label{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 16px}.stat strong{display:block;font-size:22px;color:var(--accent)}
input,select{display:block;min-width:190px;margin-top:5px;background:#0b121c;color:var(--text);border:1px solid #43566d;border-radius:8px;padding:9px 11px;font:inherit}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px;background:rgba(18,28,41,.94)}table{border-collapse:collapse;width:100%;min-width:1050px}th,td{text-align:left;padding:12px;border-bottom:1px solid var(--line);vertical-align:top}th{position:sticky;top:0;background:#152334;color:#c5d2e1;font-size:12px;letter-spacing:.07em;text-transform:uppercase}td small{display:block;color:var(--muted);font-family:ui-monospace,monospace;font-size:11px}a{color:#9ee8d5}.locator{margin-top:6px}.badge{display:inline-block;border-radius:99px;padding:2px 8px;font-size:12px}.badge.yes{background:#173b35;color:#9bf2d2}.badge.no{background:#4a3031;color:#ffb9ad}.note{border-left:3px solid var(--accent);padding:8px 14px;background:#101b27}
</style></head><body><main>
<div class="kicker">CineGraph · English pilot · offline review desk</div><h1>Actor–character evidence</h1>
<p>Cross-source candidates only. A Wikidata cast qualifier and matching Wikipedia role text are evidence to inspect, not approved credits or a claim of source agreement.</p>
<div class="stats"><div class="stat"><strong>""" + str(summary["films"]) + """</strong>films checked</div>
<div class="stat"><strong>""" + str(summary["direct_p453_links"]) + """</strong>direct P161/P453 links</div>
<div class="stat"><strong>""" + str(summary["exact_character_label_agreements"]) + """</strong>exact label agreements</div>
<div class="stat"><strong>""" + str(summary["review_required"]) + """</strong>require review</div></div>
<p class="note">Article and Wikidata links are pinned to the exact retained revisions. Review status remains required for every row. Wikipedia passage text is intentionally omitted from this report.</p>
<div class="filters"><label>Search title, actor or character<input id="search" type="search" autocomplete="off" placeholder="e.g. Ledger, Joker"></label>
<label>Film<select id="film"><option value="">All films</option>""" + options + """</select></label>
<label>Exact label match<select id="agreement"><option value="">All rows</option><option value="yes">Yes</option><option value="no">No</option></select></label>
<div class="stat" aria-live="polite"><strong id="visible-count">""" + str(len(rows)) + """</strong>visible of """ + str(len(rows)) + """ candidates</div></div>
<div class="table-wrap"><table><thead><tr><th>Film</th><th>Actor</th><th>Wikipedia role text</th><th>Wikidata label</th><th>Exact label</th><th>Source revisions / locators</th><th>Wikidata refs</th></tr></thead>
<tbody>""" + "".join(rows) + """</tbody></table></div>
<script>const search=document.querySelector('#search'),film=document.querySelector('#film'),agreement=document.querySelector('#agreement'),count=document.querySelector('#visible-count');
function filterRows(){let n=0;for(const row of document.querySelectorAll('tbody tr')){const ok=(!search.value||row.dataset.search.includes(search.value.toLocaleLowerCase()))&&(!film.value||row.dataset.film===film.value)&&(!agreement.value||row.dataset.agreement===agreement.value);row.hidden=!ok;if(ok)n++}count.textContent=String(n)}
for(const control of [search,film,agreement])control.addEventListener('input',filterRows);</script>
</main></body></html>"""
