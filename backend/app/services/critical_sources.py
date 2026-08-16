"""Register provenance-first source policies for cinema criticism and essays.

This module is intentionally a registry, not a crawler.  A source can be a
valuable route to criticism while still being inappropriate for full-text
ingestion.  Acquisition code must consult the individual work's licence and
create a ``SourceAccessPolicy`` before it fetches anything.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import DataSource


@dataclass(frozen=True)
class CriticalSourceSpec:
    name: str
    url: str
    source_type: str
    license: str
    rights_status: str
    notes: str


CRITICAL_SOURCE_REGISTRY: tuple[CriticalSourceSpec, ...] = (
    CriticalSourceSpec(
        name="Frames Cinema Journal",
        url="https://ojs.st-andrews.ac.uk/index.php/FCJ/about",
        source_type="peer_reviewed_critical_essays",
        license="CC BY 4.0 by default; verify the work",
        rights_status="review_required",
        notes=(
            "Open-access peer-reviewed film and media scholarship. The journal says authors retain copyright "
            "and articles are CC BY 4.0 unless otherwise noted. Only an individual work with that explicit licence "
            "may enter the reusable full-text layer; preserve its author, URL, licence and attribution."
        ),
    ),
    CriticalSourceSpec(
        name="OpenAlex",
        url="https://developers.openalex.org/api-reference/introduction",
        source_type="scholarly_discovery_metadata",
        license="CC0 metadata",
        rights_status="metadata_link_only",
        notes=(
            "Use only to discover work metadata and open-access locations. An OpenAlex record never grants rights "
            "to the linked paper; inspect the specific publisher or repository licence before retaining full text."
        ),
    ),
    CriticalSourceSpec(
        name="Medium",
        url="https://help.medium.com/hc/en-us/articles/213481318-Medium-Terms-of-Service",
        source_type="creator_essay_platform",
        license="Author retained; Medium receives platform licence",
        rights_status="metadata_link_only",
        notes=(
            "Store title, author, publication date and link only. Do not ingest article full text, summaries, images "
            "or embeddings without an explicit compatible licence or the author's documented permission."
        ),
    ),
    CriticalSourceSpec(
        name="Film-Philosophy",
        url="https://journals.ed.ac.uk/f-p-submissions/policies",
        source_type="peer_reviewed_critical_essays",
        license="CC BY-NC by current policy; verify the work",
        rights_status="review_required",
        notes=(
            "Useful peer-reviewed criticism, but the current policy is non-commercial. Keep it metadata/link-only "
            "unless the individual item is explicitly compatible with the deployment and product use."
        ),
    ),
    CriticalSourceSpec(
        name="NECSUS",
        url="https://doaj.org/toc/2213-0217",
        source_type="peer_reviewed_critical_essays",
        license="Article-specific; CC BY or CC BY-NC-ND",
        rights_status="review_required",
        notes=(
            "Licensing varies by article. Per-work licence verification is mandatory; CC BY-NC-ND work is not a "
            "candidate for a public reusable corpus without additional permission."
        ),
    ),
    CriticalSourceSpec(
        name="Alphaville: Journal of Film and Screen Media",
        url="https://openpolicyfinder.jisc.ac.uk/id/publication/37944",
        source_type="peer_reviewed_critical_essays",
        license="CC BY-NC-ND 4.0",
        rights_status="metadata_link_only",
        notes=(
            "Register and link to scholarship, but do not place its full text or derivative embeddings into the "
            "public corpus without a separate compatible permission."
        ),
    ),
    CriticalSourceSpec(
        name="[in]Transition",
        url="https://mediacommons.org/intransition/about-intransition",
        source_type="peer_reviewed_video_essays",
        license="Work-specific; verify text and audiovisual rights",
        rights_status="review_required",
        notes=(
            "A peer-reviewed videographic journal. Register metadata and creator statements only after inspecting "
            "the individual work licence; never ingest or redistribute audiovisual clips merely because the essay is open."
        ),
    ),
)


def register_critical_sources(db: Session) -> dict[str, int]:
    """Idempotently register source-level policy facts; it never fetches a work."""
    created = 0
    reused = 0
    for spec in CRITICAL_SOURCE_REGISTRY:
        source = db.scalar(select(DataSource).where(DataSource.name == spec.name))
        if source is None:
            db.add(DataSource(
                name=spec.name,
                url=spec.url,
                source_type=spec.source_type,
                license=spec.license,
                rights_status=spec.rights_status,
                notes=spec.notes,
            ))
            created += 1
        else:
            reused += 1
    db.flush()
    return {"created": created, "reused": reused, "registered": len(CRITICAL_SOURCE_REGISTRY)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Register critical-essay source policies without fetching content.")
    parser.add_argument("--register", action="store_true", help="Write the vetted registry to data_sources.")
    args = parser.parse_args()
    if not args.register:
        print({"registered": len(CRITICAL_SOURCE_REGISTRY), "action": "dry-run", "network_requests": 0})
        return
    with SessionLocal() as db:
        print(register_critical_sources(db))
        db.commit()


if __name__ == "__main__":
    main()
