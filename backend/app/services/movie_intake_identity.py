"""Pure identity checks for operator-selected title/year intake."""
from __future__ import annotations

from typing import Any

from app.services.wikidata_selection_resolution import is_film_in_year, title_score


def identity_issue(
    *, article_qid: str, entity: dict[str, Any], title: str,
    year: int, imdb_id: str,
) -> str | None:
    """Return a review reason unless page, EntityData and selection agree."""
    qid = str(entity.get("id") or "")
    if qid != article_qid:
        return "Wikipedia article QID does not match the retained Wikidata entity"
    if not is_film_in_year(entity, year):
        return "Wikipedia article QID does not verify as a film with the selected release year"
    if title_score(entity, title) == 0:
        return "Wikipedia article QID title/aliases do not match the selected IMDb title"
    identifiers = {
        str(claim.get("mainsnak", {}).get("datavalue", {}).get("value", ""))
        for claim in entity.get("claims", {}).get("P345", [])
    }
    if imdb_id not in identifiers:
        return "Retained Wikidata IMDb identifier does not match the selected IMDb title"
    return None
