"""Reset and seed the isolated CineGraph integration database.

This command is intentionally unable to operate on a non-test database.  It
creates a tiny, source-backed catalogue that exercises the public API without
touching the user's local research corpus or calling external services.
"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from sqlalchemy import inspect, text

from app.db import SessionLocal, engine
from app.models import (
    Assertion,
    AssertionEvidence,
    CanonicalEntity,
    DataSource,
    Film,
    FilmCredit,
    FilmGenre,
    FilmProvenance,
    Genre,
    IngestionBatch,
    LanguageEdition,
    NarrativePassage,
    Person,
    ReferenceCollection,
    ReferenceCollectionMembership,
    SourceObject,
    SourceAssertion,
    SourceSnapshot,
)
from app.services.evidence_preprocessing import build_evidence_chunks


def require_test_database() -> None:
    database = engine.url.database or ""
    if not database.endswith("_test"):
        raise RuntimeError(f"Refusing to reset non-test database: {database!r}")


def reset_database() -> None:
    require_test_database()
    table_names = inspect(engine).get_table_names()
    if not table_names:
        return
    quoted = ", ".join(f'"{name}"' for name in table_names if name != "alembic_version")
    if quoted:
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))


def add_wikidata_label_excerpt(db, source: DataSource, entity: dict) -> SourceSnapshot:
    """Replay a minimized label excerpt tied to its retained capture hash/revision."""
    qid = entity["qid"]
    label = entity["label_en"]
    entity_url = entity["entity_url"]
    capture_url = entity["capture_url"]
    source_object = SourceObject(
        source_id=source.id, external_id=qid, object_kind="entity", canonical_url=capture_url,
    )
    db.add(source_object)
    db.flush()
    snapshot = SourceSnapshot(
        source_object_id=source_object.id, source_revision=entity["source_revision"], canonical_url=capture_url,
        content_hash=entity["snapshot_sha256"], byte_size=entity["snapshot_byte_size"],
        media_type="application/json", license="CC0 1.0", attribution_url=entity_url,
        parser_version="wikidata-entitydata-excerpt-v1",
    )
    db.add(snapshot)
    db.flush()
    db.add(SourceAssertion(
        source_snapshot_id=snapshot.id, statement_locator="labels.en",
        source_property="wikidata:label:en", raw_subject={"wikidata_id": qid},
        # The retained source's label shape uses `value`; the production
        # Wikidata adapter normalizes it to the source-assertion `text` field.
        raw_value={"language": "en", "text": label}, raw_qualifiers={},
        extractor_version="wikidata-entitydata-excerpt-v1",
    ))
    return snapshot


def seed() -> None:
    reset_database()
    fixture_path = Path(__file__).with_name("fixtures") / "wikidata-dark-knight-credit-v1.json"
    wikidata_excerpt = json.loads(fixture_path.read_text(encoding="utf-8"))
    if (wikidata_excerpt.get("schema") != "cinegraph.wikidata-source-excerpt/v1"
            or wikidata_excerpt.get("license") != "CC0 1.0"):
        raise ValueError("Unsupported or unlicensed Wikidata integration excerpt.")
    entities_by_qid = {row["qid"]: row for row in wikidata_excerpt["entities"]}
    credit_excerpt = wikidata_excerpt["credit"]
    with SessionLocal() as db:
        english = LanguageEdition(
            code="en", display_name="English", native_name="English", script="Latin", enabled=True, status="live",
        )
        source = DataSource(
            name="Integration fixture source",
            url="https://example.test/cinegraph-fixture",
            source_type="recorded_test_fixture",
            license="CC0 1.0",
            rights_status="open",
            notes="Deterministic local integration fixture; no external request.",
        )
        wikidata_source = DataSource(
            name="Wikidata", url="https://www.wikidata.org/", source_type="structured_metadata",
            license="CC0 1.0", rights_status="open",
            notes="Integration-only extracted label fixture; no external request or working-corpus import.",
        )
        db.add_all([english, source, wikidata_source])
        db.flush()
        batch = IngestionBatch(source_id=source.id, external_reference="integration-fixture-v1", records_received=2, records_published=2)
        begins_entity = CanonicalEntity(entity_kind="film", canonical_label="Batman Begins (2005 film)", wikidata_id="Q166262")
        knight_entity = CanonicalEntity(entity_kind="film", canonical_label="The Dark Knight", wikidata_id="Q163872")
        nolan_entity = CanonicalEntity(entity_kind="person", canonical_label="Christopher Nolan", wikidata_id="Q25191")
        ledger_entity = CanonicalEntity(entity_kind="person", canonical_label="Heath Ledger", wikidata_id="Q40572")
        db.add_all([batch, begins_entity, knight_entity, nolan_entity, ledger_entity])
        db.flush()

        begins = Film(
            canonical_title="Batman Begins", release_date=date(2005, 6, 15), runtime_minutes=140,
            original_language_code="en", country_codes=["US", "GB"], wikidata_id="Q166262", entity_id=begins_entity.id,
        )
        knight = Film(
            # Later territory-specific release; the earliest release remains in the sourced event set.
            canonical_title="The Dark Knight", release_date=date(2022, 10, 6), runtime_minutes=152,
            original_language_code="en", country_codes=["US", "GB"], wikidata_id="Q163872", entity_id=knight_entity.id,
        )
        nolan = Person(canonical_name="Christopher Nolan", wikidata_id="Q25191", entity_id=nolan_entity.id)
        ledger = Person(canonical_name="Heath Ledger", wikidata_id="Q40572", entity_id=ledger_entity.id)
        crime = Genre(label="crime film", wikidata_id="Q959790")
        db.add_all([begins, knight, nolan, ledger, crime])
        db.flush()
        reference = "https://www.wikidata.org/wiki/Q163872"
        for qid in ("Q7743454", "Q40572"):
            add_wikidata_label_excerpt(db, wikidata_source, entities_by_qid[qid])
        film_excerpt = entities_by_qid[credit_excerpt["film_qid"]]
        film_source_object = SourceObject(
            source_id=wikidata_source.id, external_id=film_excerpt["qid"], object_kind="film",
            canonical_url=film_excerpt["capture_url"],
        )
        db.add(film_source_object)
        db.flush()
        film_credit_snapshot = SourceSnapshot(
            source_object_id=film_source_object.id, source_revision=film_excerpt["source_revision"],
            canonical_url=film_excerpt["capture_url"], content_hash=film_excerpt["snapshot_sha256"],
            byte_size=film_excerpt["snapshot_byte_size"], media_type="application/json", license="CC0 1.0",
            attribution_url=film_excerpt["entity_url"], parser_version="wikidata-entitydata-excerpt-v1",
        )
        db.add(film_credit_snapshot)
        db.flush()
        cast_statement = SourceAssertion(
            source_snapshot_id=film_credit_snapshot.id,
            statement_locator=credit_excerpt["source_locator"],
            source_property=credit_excerpt["property"],
            raw_subject={"wikidata_id": credit_excerpt["film_qid"]},
            raw_value=credit_excerpt["raw_value"],
            raw_qualifiers=credit_excerpt["raw_qualifiers"],
            extractor_version="wikidata-entitydata-excerpt-v1",
        )
        db.add(cast_statement)
        db.flush()
        cast_assertion = Assertion(
            subject_entity_id=knight_entity.id, object_entity_id=ledger_entity.id,
            object_entity_kind="person", predicate="cast", source_property=credit_excerpt["property"],
            assertion_kind="source_fact", source_id=wikidata_source.id,
            source_reference=reference, review_status="resolved",
            qualifiers=cast_statement.raw_qualifiers,
        )
        db.add(cast_assertion)
        db.flush()
        db.add(AssertionEvidence(
            assertion_id=cast_assertion.id, source_assertion_id=cast_statement.id,
            evidence_type="source_assertion",
            reference=f"{reference}#{credit_excerpt['statement_id']}",
        ))
        db.add_all([
            FilmGenre(film_id=begins.id, genre_id=crime.id, source_id=source.id, source_reference=reference),
            FilmGenre(film_id=knight.id, genre_id=crime.id, source_id=source.id, source_reference=reference),
            FilmCredit(film_id=begins.id, person_id=nolan.id, role="director", source_id=source.id, source_reference=reference),
            FilmCredit(film_id=knight.id, person_id=nolan.id, role="director", source_id=source.id, source_reference=reference),
            FilmProvenance(film_id=begins.id, source_id=source.id, batch_id=batch.id, field_name="canonical_title", source_reference="https://www.wikidata.org/wiki/Q166262"),
            FilmProvenance(film_id=knight.id, source_id=source.id, batch_id=batch.id, field_name="canonical_title", source_reference=reference),
            Assertion(
                subject_entity_id=begins_entity.id, object_entity_id=knight_entity.id, object_entity_kind="film",
                predicate="followed_by", assertion_kind="source_fact", source_id=source.id,
                source_reference=reference, review_status="published",
            ),
            Assertion(
                subject_entity_id=knight_entity.id, predicate="release_event", assertion_kind="source_fact",
                source_id=source.id, source_reference=reference, review_status="published", rank="normal",
                value_json={"type": "time", "time": "+2008-07-18T00:00:00Z", "precision": 11,
                            "calendar_model": "Q1985727"},
            ),
            Assertion(
                subject_entity_id=knight_entity.id, predicate="release_event", assertion_kind="source_fact",
                source_id=source.id, source_reference=reference, review_status="published", rank="normal",
                value_json={"type": "time", "time": "+2022-10-06T00:00:00Z", "precision": 11,
                            "calendar_model": "Q1985727"},
                qualifiers={"P291": [{"snaktype": "value", "property": "P291",
                    "datavalue": {"value": {"id": "Q851"}, "type": "wikibase-entityid"}}]},
            ),
            Assertion(
                subject_entity_id=begins_entity.id, predicate="release_event", assertion_kind="source_fact",
                source_id=source.id, source_reference="https://www.wikidata.org/wiki/Q166262",
                review_status="published", rank="normal",
                value_json={"type": "time", "time": "+2005-06-15T00:00:00Z", "precision": 11,
                            "calendar_model": "Q1985727"},
            ),
        ])
        wikipedia_source = DataSource(
            name="Integration Wikipedia narrative fixture",
            url="https://en.wikipedia.org/",
            source_type="recorded_test_fixture",
            license="CC BY-SA 4.0",
            rights_status="semantic_use_approved",
            notes="Attributable local prose fixture; no external request.",
        )
        collection = ReferenceCollection(
            code="integration-narrative-v1",
            title="Integration Narrative Collection",
            description="A two-film attributable fixture used only by the local PostgreSQL integration suite.",
            language_code="en",
            selection_method="recorded integration fixture",
            selection_version="v1",
        )
        db.add_all([wikipedia_source, collection])
        db.flush()
        source_object = SourceObject(
            source_id=wikipedia_source.id,
            external_id="The_Dark_Knight",
            object_kind="article",
            canonical_url="https://en.wikipedia.org/wiki/The_Dark_Knight",
        )
        begins_source_object = SourceObject(
            source_id=wikipedia_source.id,
            external_id="Batman_Begins",
            object_kind="article",
            canonical_url="https://en.wikipedia.org/wiki/Batman_Begins",
        )
        db.add_all([source_object, begins_source_object])
        db.flush()
        snapshot = SourceSnapshot(
            source_object_id=source_object.id,
            canonical_url=source_object.canonical_url,
            source_revision="integration-revision-1",
            content_hash="n" * 64,
            license="CC BY-SA 4.0",
            attribution_url=source_object.canonical_url,
            parser_version="fixture-v1",
        )
        begins_snapshot = SourceSnapshot(
            source_object_id=begins_source_object.id,
            canonical_url=begins_source_object.canonical_url,
            source_revision="integration-revision-1",
            content_hash="b" * 64,
            license="CC BY-SA 4.0",
            attribution_url=begins_source_object.canonical_url,
            parser_version="fixture-v1",
        )
        db.add_all([snapshot, begins_snapshot])
        db.flush()
        passage_text = (
            "Batman, Gordon, and Harvey Dent work together to dismantle Gotham's organised crime. "
            "The Joker turns that campaign into escalating public tests of law, trust, and personal moral limits. "
            "Dent is presented as the lawful public alternative to Batman, while the antagonist repeatedly forces choices that change the stakes. "
            "The final decision leaves Batman carrying blame so the city can retain a public symbol of hope."
        )
        begins_passage_text = (
            "Bruce Wayne returns to Gotham and turns fear, training, and inherited wealth into the Batman identity. "
            "His conflict with Ra's al Ghul tests whether justice can reject execution while still confronting systemic corruption. "
            "The ending establishes escalation: Batman becomes a public symbol whose presence also attracts theatrical criminals."
        )
        knight_alternative_text = (
            "The Joker stages a ferry dilemma to test whether ordinary people will sacrifice strangers to save themselves. "
            "Batman refuses the Joker's demand and turns an intrusive surveillance system off after locating him. "
            "The city's public symbol survives only after Batman takes responsibility for Dent's crimes."
        )
        begins_alternative_text = (
            "Bruce learns from the League of Shadows but rejects its demand to execute a criminal as a proof of commitment. "
            "He returns to Gotham with a public symbol built around fear, hoping to inspire a different response to corruption. "
            "That moral choice separates his mission from Ra's al Ghul's plan to destroy the city."
        )
        db.add_all([
            ReferenceCollectionMembership(
                collection_code=collection.code,
                entity_id=begins_entity.id,
                selection_position=1,
                selection_signals={"recorded_fixture": True},
                source_reference=begins_source_object.canonical_url,
            ),
            ReferenceCollectionMembership(
                collection_code=collection.code,
                entity_id=knight_entity.id,
                selection_position=2,
                selection_signals={"recorded_fixture": True},
                source_reference=source_object.canonical_url,
            ),
            NarrativePassage(
                subject_entity_id=knight_entity.id,
                source_snapshot_id=snapshot.id,
                section_locator="plot",
                section_title="Plot",
                ordinal=0,
                content=passage_text,
                content_hash="p" * 64,
                citation_markers=["fixture"],
                extraction_version="fixture-v1",
            ),
            NarrativePassage(
                subject_entity_id=begins_entity.id,
                source_snapshot_id=begins_snapshot.id,
                section_locator="plot",
                section_title="Plot",
                ordinal=0,
                content=begins_passage_text,
                content_hash="q" * 64,
                citation_markers=["fixture"],
                extraction_version="fixture-v1",
            ),
            NarrativePassage(
                subject_entity_id=knight_entity.id,
                source_snapshot_id=snapshot.id,
                section_locator="plot",
                section_title="Plot",
                ordinal=1,
                content=knight_alternative_text,
                content_hash="r" * 64,
                citation_markers=["fixture"],
                extraction_version="fixture-v1",
            ),
            NarrativePassage(
                subject_entity_id=begins_entity.id,
                source_snapshot_id=begins_snapshot.id,
                section_locator="plot",
                section_title="Plot",
                ordinal=1,
                content=begins_alternative_text,
                content_hash="s" * 64,
                citation_markers=["fixture"],
                extraction_version="fixture-v1",
            ),
        ])
        db.commit()

    # The browser/API fixture should exercise the usable evidence path, not
    # merely source passages. Keep this preprocessing local and deterministic;
    # it creates no model vectors and calls no external service.
    with SessionLocal() as db:
        report = build_evidence_chunks(db, collection_code="integration-narrative-v1")
    if report["passages_requested"] != 4 or report["passages_eligible"] != 4:
        raise RuntimeError(f"Integration narrative fixture failed preprocessing: {report}")


if __name__ == "__main__":
    seed()
