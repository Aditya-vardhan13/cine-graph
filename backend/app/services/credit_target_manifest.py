"""Select source-linked Wikidata label candidates without fetching or publishing."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.services.wikidata_raw import entity_from_entitydata

QID = re.compile(r"Q[1-9]\d*\Z")
PROPERTIES = {"P161": "cast", "P57": "director", "P58": "writer"}


def snak_qid(snak: Any) -> str | None:
    if not isinstance(snak, dict) or snak.get("snaktype") != "value":
        return None
    data = snak.get("datavalue")
    value = data.get("value") if isinstance(data, dict) else None
    qid = value.get("id") if isinstance(value, dict) else None
    return qid if isinstance(qid, str) and QID.fullmatch(qid) else None


def select_credit_target_qids(entity: dict[str, Any]) -> list[str]:
    """Select explicitly linked people and P453 characters for one film."""
    targets: set[str] = set()
    for property_id in PROPERTIES:
        for statement in entity.get("claims", {}).get(property_id, []):
            if statement.get("rank") == "deprecated":
                continue
            person = snak_qid(statement.get("mainsnak"))
            if not person:
                continue
            targets.add(person)
            for qualifier in statement.get("qualifiers", {}).get("P453", []):
                character = snak_qid(qualifier)
                if character:
                    targets.add(character)
    return sorted(targets)


def select_credit_targets(bundle: Path) -> dict[str, Any]:
    """Read retained verified film snapshots; report malformed links explicitly."""
    capture = json.loads((bundle / "capture-manifest.json").read_text(encoding="utf-8"))
    targets: dict[str, list[dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    skipped_deprecated = 0
    for film in capture["films"]:
        if film.get("identity_status") != "verified" or film.get("wikidata_status") != "captured":
            raise ValueError(f"Unverified film capture: {film.get('qid')}")
        source = (bundle / film["wikidata_snapshot_path"]).read_bytes()
        if hashlib.sha256(source).hexdigest() != film["wikidata_sha256"]:
            raise ValueError(f"Wikidata snapshot hash mismatch: {film['qid']}")
        entity = entity_from_entitydata(json.loads(source), film["qid"])
        if entity.get("lastrevid") != film["wikidata_revision"]:
            raise ValueError(f"Wikidata revision mismatch: {film['qid']}")
        for property_id, role in PROPERTIES.items():
            for index, statement in enumerate(entity.get("claims", {}).get(property_id, [])):
                locator = f"claims.{property_id}[{index}]"
                if statement.get("rank") == "deprecated":
                    skipped_deprecated += 1
                    continue
                person = snak_qid(statement.get("mainsnak"))
                if not person:
                    errors.append({"film": film["qid"], "locator": locator, "reason": "missing_person_qid"})
                    continue
                reference = {"film_qid": film["qid"], "source_revision": film["wikidata_revision"],
                             "source_sha256": film["wikidata_sha256"], "statement_locator": locator, "role": role}
                targets.setdefault(person, []).append(reference)
                for qualifier_index, qualifier in enumerate(statement.get("qualifiers", {}).get("P453", [])):
                    character = snak_qid(qualifier)
                    if not character:
                        errors.append({"film": film["qid"], "locator": f"{locator}.qualifiers.P453[{qualifier_index}]", "reason": "missing_character_qid"})
                        continue
                    targets.setdefault(character, []).append({**reference, "role": "character",
                        "person_qid": person, "qualifier_locator": f"qualifiers.P453[{qualifier_index}]"})
    return {"schema": "cinegraph.credit-target-manifest/v1", "selection_sha256": capture.get("selection_sha256"),
            "films": len(capture["films"]), "targets": [{"qid": qid, "references": refs} for qid, refs in sorted(targets.items())],
            "deprecated_skipped": skipped_deprecated, "exceptions": errors}
