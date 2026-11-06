"""Extract review-only actor/character candidates from retained cast prose.

This adapter never fetches, writes to the catalog, or promotes narrative text
to an operational fact. It recognizes explicit ``Actor as Character`` phrases
inside cast-labelled Wikipedia passages and retains their source span. Actor
names without a captured Wikidata identity remain unresolved source candidates.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


ADAPTER_VERSION = "wikipedia-cast-explicit-as-candidates-v7"
CAST_SECTION_NAMES = {
    "cast", "cast-and-characters", "cast-and-crew", "cast-characters",
    "cast-members", "main-cast", "principal-cast", "voice-cast",
    "voice-cast-and-characters",
}
ABBREVIATIONS = {"dr", "mr", "mrs", "ms", "prof", "st", "jr", "sr", "rev"}
SOURCE_NAME = re.compile(
    r'(?<![\w])(?P<actor>(?:(?:[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ\'’-]*[.]?|'
    r'"[^"]+")[ \t]+){1,4}[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ\'’-]*[.]?'
    r'(?:[ \t]+(?:Jr|Sr|II|III|IV|V)\.?)?)[ \t]+as[ \t]+'
)


def is_cast_section(locator: str) -> bool:
    """Match explicit cast section path components, not ``casting`` prose."""
    return any(part in CAST_SECTION_NAMES for part in locator.casefold().split("/"))


def _first_character_name(value: str) -> str:
    """Conservatively retain the name after ``as`` before descriptive prose."""
    value = re.split(r"[,;:\n(]", value, maxsplit=1)[0]
    for boundary in re.finditer(r"[.!?]\s+(?=[A-Z“\"])", value):
        previous_word = value[:boundary.start()].rstrip().rsplit(" ", 1)[-1]
        if (previous_word.casefold().rstrip(".") not in ABBREVIATIONS
                and not re.fullmatch(r"[A-Z][.]?", previous_word, flags=re.IGNORECASE)):
            value = value[:boundary.start()]
            break
    value = re.sub(r"\s+(?:and|or)$", "", value.strip(), flags=re.IGNORECASE)
    return value.strip(" \t\r\n,;:.!?‘’\"“”")


def _label_key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold().strip("‘’\"“”")


def resolve_source_actor_identities(
    candidates: list[dict[str, Any]], people: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach exact captured Wikidata person-identity candidates, never credits.

    A unique English label is preferred to an English alias. Ambiguous matches
    retain all candidate QIDs; fuzzy or transliterated matching is deliberately
    out of scope. This does not prove that a person was credited in the film.
    """
    labels: dict[str, list[dict[str, Any]]] = {}
    aliases: dict[str, list[dict[str, Any]]] = {}
    people_by_qid: dict[str, dict[str, Any]] = {}
    for person in people:
        qid, label = person.get("qid"), person.get("label")
        if not isinstance(qid, str) or not isinstance(label, str) or not label.strip():
            continue
        row = {**person, "qid": qid, "label": label.strip()}
        people_by_qid[qid] = row
        labels.setdefault(_label_key(label), []).append(row)
        for alias in person.get("aliases", []):
            if isinstance(alias, str) and alias.strip():
                aliases.setdefault(_label_key(alias), []).append(row)

    resolved: list[dict[str, Any]] = []
    for original in candidates:
        candidate = dict(original)
        if candidate.get("actor_qid"):
            person = people_by_qid.get(candidate["actor_qid"])
            candidate.update({
                "actor_identity_qid": candidate["actor_qid"],
                "actor_identity_label": person.get("label") if person else candidate.get("actor_label"),
                "actor_identity_match": "same_film_wikidata_cast_target",
                "identity_resolution": "same_film_wikidata_cast_target",
            })
            if person:
                candidate["actor_identity_evidence"] = {
                    "source_url": person.get("source_url"),
                    "source_revision": person.get("source_revision"),
                    "snapshot_sha256": person.get("snapshot_sha256"),
                }
            resolved.append(candidate)
            continue
        name_key = _label_key(str(candidate.get("actor_label_in_source", "")))
        matches = labels.get(name_key, [])
        match_type = "exact_unique_english_label"
        if not matches:
            matches = aliases.get(name_key, [])
            match_type = "exact_unique_english_alias"
        unique = {row["qid"]: row for row in matches}
        if len(unique) == 1:
            person = next(iter(unique.values()))
            candidate.update({
                "actor_identity_qid": person["qid"],
                "actor_identity_label": person["label"],
                "actor_identity_match": match_type,
                "actor_identity_evidence": {
                    "source_url": person.get("source_url"),
                    "source_revision": person.get("source_revision"),
                    "snapshot_sha256": person.get("snapshot_sha256"),
                },
                "identity_resolution": "matched_captured_person_identity_only",
            })
        elif len(unique) > 1:
            candidate.update({
                "actor_identity_qid": None,
                "actor_identity_match": "ambiguous_exact_label_or_alias",
                "candidate_actor_identity_qids": sorted(unique),
                "identity_resolution": "ambiguous_captured_person_identity",
            })
        else:
            candidate.update({
                "actor_identity_qid": None,
                "actor_identity_match": "no_exact_captured_person_label_or_alias",
                "identity_resolution": "unresolved_source_name",
            })
        resolved.append(candidate)
    return resolved


def _passage_hash(passage: dict[str, Any]) -> str:
    content = passage.get("content")
    if not isinstance(content, str):
        raise ValueError("Cast passage content must be text")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    recorded = passage.get("content_sha256")
    if recorded is not None and recorded != digest:
        raise ValueError("Cast passage content hash does not match its text")
    return digest


def extract_cast_candidates(
    *,
    film_qid: str,
    passages: list[dict[str, Any]],
    actors: list[dict[str, Any]],
    character_labels_by_actor: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    """Return source-bound candidates and ambiguities for one captured film.

    ``actors`` contains only explicitly sourced cast QIDs and captured English
    labels. Duplicate English labels are quarantined as ambiguous instead of
    being assigned to an arbitrary QID. Candidate names remain literal text.
    """
    actors_by_qid: dict[str, dict[str, Any]] = {}
    for actor in actors:
        qid, label = actor.get("qid"), actor.get("label")
        if not isinstance(qid, str) or not isinstance(label, str) or not label.strip():
            continue
        row = actors_by_qid.setdefault(qid, {"qid": qid, "label": label.strip(),
                                              "statement_locators": []})
        if row["label"] != label.strip():
            raise ValueError(f"Actor QID {qid} has conflicting captured English labels")
        locators = actor.get("statement_locators", [])
        if not isinstance(locators, list) or any(not isinstance(value, str) for value in locators):
            raise ValueError(f"Actor statement locators must be text for {qid}")
        row["statement_locators"].extend(locators)

    labels_to_actors: dict[str, list[dict[str, Any]]] = {}
    for actor in actors_by_qid.values():
        actor["statement_locators"] = sorted(set(actor["statement_locators"]))
        labels_to_actors.setdefault(_label_key(actor["label"]), []).append(actor)

    label_spellings = {
        key: sorted({actor["label"] for actor in values}, key=lambda item: (-len(item), item.casefold()))[0]
        for key, values in labels_to_actors.items()
    }
    alternatives = sorted(label_spellings.values(), key=lambda item: (-len(item), item.casefold()))
    expression = (re.compile(
        r"(?<![\w])(?P<actor>" + "|".join(re.escape(label) for label in alternatives)
        + r")(?![\w])\s+as\s+", re.IGNORECASE
    ) if alternatives else None)

    candidates: list[dict[str, Any]] = []
    ambiguities: list[dict[str, Any]] = []
    cast_passages = 0
    for passage in passages:
        locator = passage.get("section_locator")
        if not isinstance(locator, str) or not is_cast_section(locator):
            continue
        cast_passages += 1
        passage_hash = _passage_hash(passage)
        content = passage["content"]
        # First bind exact known cast labels; then retain other explicit
        # source-name patterns as unresolved candidates for human identity
        # review. Never infer an actor QID from Wikipedia prose alone.
        known_matches = list(expression.finditer(content)) if expression else []
        discovered = [(match, True) for match in known_matches]
        known_spans = [(match.start(), match.end()) for match in known_matches]
        for match in SOURCE_NAME.finditer(content):
            if any(match.start() < end and match.end() > start for start, end in known_spans):
                continue
            discovered.append((match, False))
        discovered.sort(key=lambda value: value[0].start())
        for index, (match, known_match) in enumerate(discovered):
            label_key = _label_key(match.group("actor"))
            matching_actors = labels_to_actors.get(label_key, []) if known_match else []
            end = discovered[index + 1][0].start() if index + 1 < len(discovered) else len(content)
            character_name = _first_character_name(content[match.end():end])
            evidence_phrase = content[match.start():end].strip()
            common = {
                "film_qid": film_qid,
                "actor_label_in_source": match.group("actor"),
                "character_name_in_source": character_name,
                "evidence_phrase": evidence_phrase[:240],
                "section_locator": locator,
                "section_title": passage.get("section_title"),
                "passage_ordinal": passage.get("ordinal"),
                "passage_sha256": passage_hash,
            }
            clause_start = max(content.rfind(mark, 0, match.start())
                               for mark in (".", "!", "?", ";", "\n")) + 1
            prefix = content[clause_start:match.start()]
            if re.search(r",\s+.*\band\s+$", prefix, flags=re.IGNORECASE):
                ambiguities.append({**common, "candidate_actor_qids": sorted(
                    actor["qid"] for actor in matching_actors),
                    "reason": "group_role_not_individualized"})
                continue
            if not known_match:
                if re.search(r"\b\d+(?:st|nd|rd|th)[ \t]+$", prefix, flags=re.IGNORECASE):
                    ambiguities.append({**common, "candidate_actor_qids": [],
                                        "reason": "nonperson_ordinal_prefix"})
                    continue
                if (len(match.group("actor").split()) > 3
                        and not re.search(r'["“][^"”]+["”]', match.group("actor"))):
                    ambiguities.append({**common, "candidate_actor_qids": [],
                                        "reason": "actor_name_span_overlong"})
                    continue
                if not character_name:
                    ambiguities.append({**common, "candidate_actor_qids": [],
                                        "reason": "empty_character_name"})
                    continue
                candidates.append({
                    **common,
                    "actor_qid": None,
                    "actor_label": None,
                    "actor_statement_locators": [],
                    "matching_wikidata_character_qids": [],
                    "identity_resolution": "unresolved_source_name",
                    "review_status": "review_required",
                })
                continue
            if len(matching_actors) != 1:
                ambiguities.append({**common, "candidate_actor_qids": sorted(
                    actor["qid"] for actor in matching_actors),
                    "reason": "ambiguous_actor_label" if matching_actors else "unmatched_actor_label"})
                continue
            if not character_name:
                ambiguities.append({**common, "candidate_actor_qids": [matching_actors[0]["qid"]],
                                    "reason": "empty_character_name"})
                continue
            actor = matching_actors[0]
            known_character_ids = sorted({
                row["qid"] for row in (character_labels_by_actor or {}).get(actor["qid"], [])
                if _label_key(row.get("label", "")) == _label_key(character_name)
            })
            candidates.append({
                **common,
                "actor_qid": actor["qid"],
                "actor_label": actor["label"],
                "actor_statement_locators": actor["statement_locators"],
                "matching_wikidata_character_qids": known_character_ids,
                "review_status": "review_required",
            })

    candidates.sort(key=lambda row: (
        row["film_qid"], row["actor_qid"] or "", _label_key(row["character_name_in_source"]),
        row["section_locator"] or "", row["passage_ordinal"] or 0,
    ))
    ambiguities.sort(key=lambda row: (
        row["film_qid"], row["section_locator"] or "", row["passage_ordinal"] or 0,
        row["actor_label_in_source"].casefold(),
    ))
    return {"cast_passage_count": cast_passages, "candidates": candidates,
            "ambiguities": ambiguities}
