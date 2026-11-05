"""Explicit local pilot replay; no network and never the working corpus."""
import hashlib
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Assertion, AssertionEvidence, CanonicalEntity, EvidenceChunk, Film, LanguageEdition, NarrativePassage, RawIngestionRun, ReferenceCollection, ReferenceCollectionMembership, SourceAssertion, SourceObject, SourceSnapshot
from app.services.current_narrative_passages import current_passage_rows
from app.services.evidence_preprocessing import ChunkConfiguration, build_evidence_chunks, evidence_chunk_quality_report
from app.services.movie_intake_worker import has_plot
from app.services.imdb_dataset import ImdbDataset
from app.services.movie_data_gateway import IMDB_SOURCE, IMDB_VERSION, persist_movie_bundle, source_registration
from app.services.movie_source_facts import imdb_facts
from app.services.research_catalog import research_films_from_entities
from app.services.research_credits import sourced_credit_groups
from app.services.source_assertion_projection import project_source_assertions
from app.services.wikidata import source_for_wikidata
from app.services.wikidata_raw import ADAPTER_VERSION as WIKIDATA_ADAPTER_VERSION, entity_from_entitydata, ingest_selected_credit_labels, persist_entity_capture, persist_english_label_capture, wikidata_entitydata_policy
from app.services.wikipedia_article_html import parse_article_html
from app.services.wikipedia_raw import ADAPTER_VERSION, persist_article_snapshot, source_for_wikipedia, wikipedia_article_html_policy
from app.services.wikipedia_research import ARTICLE_HTML_EXTRACTION_VERSION, extract_passages
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_retained_pilot_replays_into_isolated_database(tmp_path: Path) -> None:
    bundle_name = os.environ.get("CINEGRAPH_PILOT_BUNDLE")
    if not bundle_name:
        pytest.skip("explicit local pilot bundle required")
    bundle = Path(bundle_name).resolve()
    manifest = json.loads((bundle / "capture-manifest.json").read_text())
    films = manifest["films"]
    assert len(films) == 10
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(code="en", display_name="English", native_name="English", script="Latin", enabled=True, status="live"))
        db.add(ReferenceCollection(code="local-pilot-ten", title="Local pilot", description="Isolated replay", language_code="en", selection_method="retained_manifest", selection_version="1"))
        db.flush()
        source = source_for_wikipedia(db)
        policy = wikipedia_article_html_policy(db, source, robots_sha256=manifest["wikipedia_robots_sha256"])
        run = RawIngestionRun(source_id=source.id, access_policy_id=policy.id,
                              adapter_name="wikipedia_article_html_snapshot", adapter_version=ADAPTER_VERSION,
                              status="running", records_requested=len(films))
        db.add(run)
        db.flush()
        total = 0
        for film in films:
            assert film["identity_status"] == "verified" and film["wikipedia_status"] == "captured"
            payload = (bundle / film["wikipedia_snapshot_path"]).read_bytes()
            assert hashlib.sha256(payload).hexdigest() == film["wikipedia_sha256"]
            document = parse_article_html(payload, canonical_url=film["wikipedia_capture_url"], expected_qid=film["qid"])
            assert document.metadata.revision_id == film["wikipedia_revision"]
            snapshot, created, _ = persist_article_snapshot(db, source=source, run=run, payload=payload,
                                                             document=document, media_type="text/html", storage_root=tmp_path)
            assert created and snapshot.content_hash == film["wikipedia_sha256"]
            db.commit()
            result = extract_passages(db, film["qid"])
            replay = extract_passages(db, film["qid"])
            assert result["passages_created"] == len(document.passages)
            assert replay["passages_created"] == 0
            rows = current_passage_rows(db, {next(iter(result["passages"].values()))[0].subject_entity_id})
            assert len(rows) == len(document.passages)
            assert all(p.extraction_version == ARTICLE_HTML_EXTRACTION_VERSION and s.id == snapshot.id for p, s in rows)
            assert has_plot(db, rows[0][0].subject_entity_id)
            db.add(ReferenceCollectionMembership(collection_code="local-pilot-ten", entity_id=rows[0][0].subject_entity_id,
                                                 source_reference=film["wikipedia_capture_url"]))
            db.commit()
            total += len(rows)
        assert total == 484
        wikidata = source_for_wikidata(db)
        wikidata_policy = wikidata_entitydata_policy(db, wikidata, robots_sha256=manifest["wikidata_robots_sha256"])
        wikidata_run = RawIngestionRun(source_id=wikidata.id, access_policy_id=wikidata_policy.id,
                                       adapter_name="wikidata_entity_json", adapter_version=WIKIDATA_ADAPTER_VERSION,
                                       status="running", records_requested=len(films))
        db.add(wikidata_run)
        db.commit()
        for film in films:
            payload = (bundle / film["wikidata_snapshot_path"]).read_bytes()
            assert hashlib.sha256(payload).hexdigest() == film["wikidata_sha256"]
            entity = entity_from_entitydata(json.loads(payload), film["qid"])
            assert entity["lastrevid"] == film["wikidata_revision"]
            created, statements = persist_entity_capture(db, source=wikidata, run=wikidata_run, qid=film["qid"],
                                                          entity=entity, payload=payload, snapshot_root=tmp_path)
            assert created and statements > 0
            db.commit()
        projection = project_source_assertions(db, collection_code="local-pilot-ten")
        again = project_source_assertions(db, collection_code="local-pilot-ten")
        assert projection["assertions_created"] > 0 and again["assertions_created"] == 0
        links = db.execute(select(Assertion, SourceAssertion).join(AssertionEvidence, AssertionEvidence.assertion_id == Assertion.id)
                           .join(SourceAssertion, SourceAssertion.id == AssertionEvidence.source_assertion_id)).all()
        assert len(links) == projection["assertions_created"]
        assert all(assertion.qualifiers == raw.raw_qualifiers for assertion, raw in links)
        canary_name = os.environ.get("CINEGRAPH_CREDIT_CANARY")
        if canary_name:
            canary = Path(canary_name).resolve()
            canary_manifest = json.loads((canary / "manifest.json").read_text())
            film = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == "Q163872"))
            assert not sourced_credit_groups(db, film.id)
            for item in canary_manifest["entities"]:
                payload = (canary / item["snapshot_path"]).read_bytes()
                assert hashlib.sha256(payload).hexdigest() == item["sha256"]
                entity = entity_from_entitydata(json.loads(payload), item["qid"])
                assert entity["lastrevid"] == item["source_revision"]
                persist_entity_capture(db, source=wikidata, run=wikidata_run, qid=item["qid"], entity=entity,
                                       payload=payload, snapshot_root=tmp_path)
                db.commit()
                label = db.scalar(select(SourceAssertion).join(SourceSnapshot).join(SourceObject).where(
                    SourceObject.external_id == item["qid"], SourceAssertion.source_property == "wikidata:label:en"))
                assert label and label.raw_value == {"language": "en", "text": item["english_label"]}
                if item["qid"] == "Q45772":
                    actor_only = next(c for g in sourced_credit_groups(db, film.id) for c in g.credits if c.name == "Christian Bale")
                    assert actor_only.character_name is None
            actor = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == "Q45772"))
            cast = next(raw for assertion, raw in links if assertion.subject_entity_id == film.id
                        and assertion.object_entity_id == actor.id and assertion.predicate == "cast")
            assert any(s.get("datavalue", {}).get("value", {}).get("id") == "Q78607187"
                       for s in cast.raw_qualifiers.get("P453", []))
            groups = sourced_credit_groups(db, film.id)
            credit = next(c for group in groups for c in group.credits if c.name == "Christian Bale")
            assert credit.character_name == "Bruce Wayne"
            assert credit.name_source_revision and credit.character_source_revision
            assert credit.name_source_url and credit.character_source_url
            print("pilot credit canary: retained film statement links source-backed actor and character QIDs")
        credit_labels_name = os.environ.get("CINEGRAPH_CREDIT_LABELS")
        if credit_labels_name:
            credit_bundle = Path(credit_labels_name).resolve()
            checkpoint = json.loads((credit_bundle / "checkpoint.json").read_text())
            target_manifest_path = credit_bundle.parent / "credit-targets-v1.json"
            target_manifest_bytes = target_manifest_path.read_bytes()
            target_manifest = json.loads(target_manifest_bytes)
            assert checkpoint["manifest_sha256"] == hashlib.sha256(target_manifest_bytes).hexdigest()
            assert len(checkpoint["captured"]) == len(target_manifest["targets"]) == 445
            labels_newly_asserted = labels_missing = 0
            for qid, item in checkpoint["captured"].items():
                payload = (credit_bundle / item["snapshot_path"]).read_bytes()
                assert hashlib.sha256(payload).hexdigest() == item["sha256"]
                entity = entity_from_entitydata(json.loads(payload), qid)
                assert entity["lastrevid"] == item["source_revision"]
                assert entity.get("labels", {}).get("en", {}).get("value") == item["english_label"]
                created, count = persist_english_label_capture(
                    db, source=wikidata, run=wikidata_run, qid=qid, entity=entity,
                    payload=payload, canonical_url=item["source_url"], snapshot_root=tmp_path,
                )
                assert count in (0, 1)
                labels_newly_asserted += count
                labels_missing += item["english_label"] is None
                db.commit()
            first_qid = next(iter(checkpoint["captured"]))
            first_item = checkpoint["captured"][first_qid]
            first_payload = (credit_bundle / first_item["snapshot_path"]).read_bytes()
            first_entity = entity_from_entitydata(json.loads(first_payload), first_qid)
            replay_created, replay_assertions = persist_english_label_capture(
                db, source=wikidata, run=wikidata_run, qid=first_qid, entity=first_entity,
                payload=first_payload, canonical_url=first_item["source_url"], snapshot_root=tmp_path,
            )
            assert not replay_created and replay_assertions == 0
            db.commit()
            labels_asserted = len(db.scalars(select(SourceAssertion.id).join(SourceSnapshot).join(SourceObject).where(
                SourceObject.external_id.in_(checkpoint["captured"]),
                SourceAssertion.source_property == "wikidata:label:en",
            ).distinct()).all())
            assert labels_asserted == 440 and labels_newly_asserted == 438 and labels_missing == 5
            reused = ingest_selected_credit_labels(
                db, list(checkpoint["captured"]), manifest_uri="integration:credit-label-reuse",
            )
            assert reused["snapshots_created"] == reused["source_assertions_created"] == 0
            assert reused["snapshots_reused"] == 445 and reused["without_english_label"] == 5
            names_by_film = {
                str(subject.wikidata_id): sourced_credit_groups(db, subject.id)
                for subject in db.scalars(select(CanonicalEntity).where(
                    CanonicalEntity.wikidata_id.in_([f["qid"] for f in films])
                ))
            }
            assert len(names_by_film) == 10
            assert all(any(group.credits for group in groups) for groups in names_by_film.values())
            named_cast = sum(
                1 for groups in names_by_film.values()
                if any(credit.role == "cast" for group in groups for credit in group.credits)
            )
            named_characters = sum(
                1 for groups in names_by_film.values()
                if any(credit.role == "cast" and credit.character_name
                       for group in groups for credit in group.credits)
            )
            assert named_cast == 10
            print("pilot retained credit labels:", json.dumps({
                "targets": len(checkpoint["captured"]), "english_labels": labels_asserted,
                "new_english_labels": labels_newly_asserted,
                "without_english_label": labels_missing, "films_with_named_cast": named_cast,
                "films_with_named_characters": named_characters,
                "films_without_named_characters": [
                    title for film, title in ((f["qid"], f["title"]) for f in films)
                    if not any(credit.role == "cast" and credit.character_name
                               for group in names_by_film.get(film, ()) for credit in group.credits)
                ],
            }, sort_keys=True))
        subjects = list(db.scalars(select(CanonicalEntity).where(CanonicalEntity.wikidata_id.in_([f["qid"] for f in films]))))
        profiles = research_films_from_entities(db, subjects)
        credits = {str(subject.wikidata_id): sourced_credit_groups(db, subject.id) for subject in subjects}
        display = {"films": len(profiles), "release_years": sum(p.release_year is not None for p in profiles),
                   "films_with_sourced_credits": sum(bool(groups) for groups in credits.values()),
                   "films_with_character_names": sum(any(c.character_name for g in groups for c in g.credits) for groups in credits.values())}
        print("pilot structured projection:", json.dumps({"scanned": projection["statements_scanned"], "created": projection["assertions_created"], "display": display}, sort_keys=True))
        if os.environ.get("CINEGRAPH_IMDB_LOCAL") == "1":
            root = bundle.parents[3]
            dataset = ImdbDataset(root / "imdb_data", root / "data/imdb_index")
            imdb_source, imdb_policy = source_registration(db, IMDB_SOURCE)
            imdb_run = RawIngestionRun(source_id=imdb_source.id, access_policy_id=imdb_policy.id,
                                       adapter_name="imdb_local_pilot", adapter_version=IMDB_VERSION,
                                       status="running", records_requested=len(films))
            db.add(imdb_run)
            db.commit()
            for entry in films:
                entity = next(s for s in subjects if s.wikidata_id == entry["qid"])
                payload = json.loads((bundle / entry["wikidata_snapshot_path"]).read_text())
                wd = entity_from_entitydata(payload, entry["qid"])
                ids = [s.get("mainsnak", {}).get("datavalue", {}).get("value") for s in wd.get("claims", {}).get("P345", []) if s.get("rank") != "deprecated"]
                assert len(ids) == 1 and isinstance(ids[0], str)
                movie = dataset.film_bundle(ids[0])
                assert movie["basics"]["startYear"] == str(entry["year"])
                profile = Film(canonical_title=entry["title"], original_language_code="en", country_codes=[],
                               wikidata_id=entry["qid"], entity_id=entity.id, review_status="review_required")
                db.add(profile)
                db.flush()
                persist_movie_bundle(db, run=imdb_run, source=imdb_source, external_id=ids[0], film=profile,
                                     bundle=movie, facts=imdb_facts(movie), canonical_url=f"https://www.imdb.com/title/{ids[0]}/",
                                     revision=None, snapshot_root=tmp_path)
                db.commit()
                assert not sourced_credit_groups(db, entity.id)
                local = sourced_credit_groups(db, entity.id, include_noncommercial=True)
                assert any(c.character_name for g in local for c in g.credits if c.role == "cast")
            print("pilot restricted IMDb credits: 10/10 films have local character credits; excluded by default")
        config = ChunkConfiguration(source_parser_version=ADAPTER_VERSION, extraction_version=ARTICLE_HTML_EXTRACTION_VERSION)
        first = build_evidence_chunks(db, collection_code="local-pilot-ten", config=config)
        second = build_evidence_chunks(db, collection_code="local-pilot-ten", config=config)
        report = evidence_chunk_quality_report(db, collection_code="local-pilot-ten", config=config)
        assert first["passages_requested"] == total and first["passages_eligible"] == total
        assert first["chunks_created"] > 0 and second["chunks_created"] == 0
        assert second["chunks_reused"] == first["chunks_created"]
        assert report["eligible_chunks_per_film"]["films_with_eligible_chunks"] == 10
        chunks = list(db.scalars(select(EvidenceChunk)))
        assert len(chunks) == report["chunk_count"]
        for chunk in chunks:
            passage = db.get(NarrativePassage, chunk.narrative_passage_id)
            assert passage and chunk.subject_entity_id == passage.subject_entity_id
            assert all(position in passage.citation_positions for position in chunk.citation_positions)
        print("pilot chunk report:", json.dumps(report, sort_keys=True))
