import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base
from app.admin_intake import enqueue_films, imdb_id_from_input
from app.models import (
    Assertion, AssertionEvidence, CanonicalEntity, DataSource, Film, LanguageEdition,
    MovieIntakeJob, ReferenceCollection, ReferenceCollectionMembership, SourceAssertion, SourceSnapshot,
)
from app.services.imdb_dataset import ImdbDataset, build_index
from app.services.movie_intake_worker import claim_next
from app.services.actor_filmography import match_row, parse_filmography
from app.services.indian_film_selection import (
    Candidate, LANGUAGES, ambiguous_imdb_qids, parse_candidates, select_manifest, sparql_query,
)
from app.services.indian_wikipedia_manifest import build_manifests
from app.services.indian_narrative_jobs import listed_chunk_paths
from app.services.raw_snapshots import snapshot, source_object
from app.services.wikidata_raw import wikidata_api_policy
from app.services.movie_data_gateway import (
    IMDB_SOURCE, TMDB_SOURCE, cached_tmdb_id, persist_movie_bundle, resolve_seed,
    retract_replaced_identifier, source_registration,
    start_run, MovieSeed,
)
from app.services.movie_source_facts import imdb_facts, tmdb_facts
from app.services.reconcile_manifest_languages import reconcile_one as reconcile_language
from app.services.research_metadata import language_code_for_qids
from app.services.review_wikidata_imdb_ids import review_one as review_wikidata_imdb_id
from app.services.audit_movie_collection import (
    audit_collection, compare_source_metadata, section_coverage,
)
from app.services.wikidata_imdb_resolver import imdb_qid_query, qids_by_imdb
from tests.postgres_test_db import isolated_postgres_engine


def _mini_dataset(root: Path) -> tuple[ImdbDataset, dict]:
    data = root / "imdb_data"
    data.mkdir()
    (data / "title.basics.tsv").write_text(
        "tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n"
        "tt0000001\tmovie\tA Film\tA Film\t0\t2008\t\\N\t152\tAction,Drama\n",
        encoding="utf-8",
    )
    (data / "title.akas.tsv").write_text(
        "titleId\tordering\ttitle\tregion\tlanguage\ttypes\tattributes\tisOriginalTitle\n"
        "tt0000001\t1\tA Film\tIN\tte\t\\N\t\\N\t0\n",
        encoding="utf-8",
    )
    (data / "title.crew.tsv").write_text(
        "tconst\tdirectors\twriters\n"
        "tt0000001\tnm0000002\tnm0000002\n",
        encoding="utf-8",
    )
    (data / "title.principals.tsv").write_text(
        "tconst\tordering\tnconst\tcategory\tjob\tcharacters\n"
        'tt0000001\t1\tnm0000001\tactor\t\\N\t["The Hero"]\n'
        "tt0000001\t2\tnm0000002\tdirector\t\\N\t\\N\n",
        encoding="utf-8",
    )
    (data / "title.ratings.tsv").write_text(
        "tconst\taverageRating\tnumVotes\n"
        "tt0000001\t8.4\t1000\n",
        encoding="utf-8",
    )
    (root / "name.basics.tsv").write_text(
        "nconst\tprimaryName\tbirthYear\tdeathYear\tprimaryProfession\tknownForTitles\n"
        "nm0000001\tActor One\t\\N\t\\N\tactor\ttt0000001\n"
        "nm0000002\tDirector Two\t\\N\t\\N\tdirector\ttt0000001\n",
        encoding="utf-8",
    )
    index = root / "index"
    build_index(data, index)
    dataset = ImdbDataset(data, index)
    return dataset, dataset.film_bundle("tt0000001")


def test_sparse_tsv_gateway_and_role_extraction(tmp_path) -> None:
    dataset, bundle = _mini_dataset(tmp_path)
    assert dataset.search_title("A Film", 2008)[0]["tconst"] == "tt0000001"
    assert resolve_seed(dataset, MovieSeed("A Film", 2008)) == (
        "tt0000001", "unique_exact_title_year",
    )
    assert resolve_seed(dataset, MovieSeed("A Film 2", 2008))[0] is None
    facts = imdb_facts(bundle)
    cast = next(fact for fact in facts if fact.predicate == "cast")
    assert cast.value["name"] == "Actor One"
    assert cast.value["characters"] == ["The Hero"]
    assert next(fact for fact in facts if fact.predicate == "audience_rating").value["votes"] == 1000
    assert bundle["dataset_sha256"]["basics"]


def test_sparse_seek_keeps_duplicate_ids_across_multiple_blocks(tmp_path) -> None:
    data = tmp_path / "imdb_data"
    data.mkdir()
    (data / "title.akas.tsv").write_text(
        "titleId\tordering\ttitle\n" +
        "".join(f"tt0000001\t{number}\tAlias {number}\n" for number in range(8200)) +
        "tt0000002\t1\tOther\n",
        encoding="utf-8",
    )
    index = tmp_path / "index"
    build_index(data, index, kinds=("akas",))
    assert len(ImdbDataset(data, index).rows("akas", "tt0000001")) == 8200


def test_tmdb_facts_preserve_country_dates_cast_roles_and_restricted_keywords() -> None:
    facts = tmdb_facts({
        "title": "A Film", "release_date": "2008-07-18", "runtime": 152,
        "credits": {"cast": [{"id": 1, "name": "Actor One", "character": "The Hero", "order": 0}], "crew": []},
        "release_dates": {"results": [{"iso_3166_1": "IN", "release_dates": [
            {"release_date": "2008-07-25T00:00:00.000Z", "type": 3, "certification": "UA"},
        ]}]},
        "keywords": {"keywords": [{"id": 12, "name": "test theme"}]},
    })
    assert any(f.predicate == "cast" and f.value["character"] == "The Hero" for f in facts)
    assert any(f.predicate == "release_event" and f.value.get("country") == "IN" for f in facts)
    assert any(f.predicate == "source_keyword" and f.review_status == "review_required" for f in facts)


def test_filmography_parser_carries_year_and_requires_manifest_match() -> None:
    rows = parse_filmography('''== Filmography ==
{| class="wikitable"
! Year
! Title
|-
| rowspan="2" |2007
! scope="row" |''[[First film|First]]''
|Hero
|-
! scope="row" |''[[Second film|Second]]''
|Himself
|}
''')
    assert [(row.year, row.title, row.character) for row in rows] == [
        (2007, "First", "Hero"), (2007, "Second", "Himself"),
    ]
    assert match_row(rows[1], [MovieSeed("Second", 2007)]) == MovieSeed("Second", 2007)
    assert match_row(rows[1], [MovieSeed("Second", 2008)]) is None


def test_indian_candidate_requires_wikidata_and_local_imdb_agreement(tmp_path) -> None:
    dataset, _ = _mini_dataset(tmp_path)
    raw = {"payload": {"results": {"bindings": [
        {"item": {"value": "http://www.wikidata.org/entity/Q123"},
         "imdb": {"value": "tt0000001"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q124"},
         "imdb": {"value": "tt9999999"}},
    ]}}}
    candidates, rejected = parse_candidates(raw, "te", dataset)
    assert [(item.wikidata_id, item.imdb_id, item.votes) for item in candidates] == [
        ("Q123", "tt0000001", 1000),
    ]
    assert rejected == {"not_single_nonadult_movie": 1}
    assert "wdt:P495 wd:Q668" in sparql_query(LANGUAGES["te"][0], 5)


def test_multiple_original_languages_are_not_arbitrarily_collapsed() -> None:
    assert language_code_for_qids({"Q8097", "Q36236"}) == "mul"
    assert language_code_for_qids({"Q8097"}) == "te"
    assert language_code_for_qids(set()) == "und"


def test_candidate_selection_requires_review_for_duplicate_wikidata_imdb_ids() -> None:
    by_language = {}
    next_id = 1
    for code, (_, quota) in LANGUAGES.items():
        rows = []
        for _ in range(quota + 2):
            rows.append(Candidate(f"tt{next_id:07d}", f"Q{next_id}", code,
                                  f"Film {next_id}", 2000, 8.0, 1000, 8.0))
            next_id += 1
        by_language[code] = rows
    first = by_language["hi"][0]
    by_language["te"].append(Candidate(first.imdb_id, "Q9999", "te", first.title,
                                       first.year, first.rating, first.votes, first.weighted_score))
    assert ambiguous_imdb_qids(by_language)[first.imdb_id] == ["Q1", "Q9999"]
    unreviewed, _ = select_manifest(by_language)
    assert first.imdb_id not in {row.imdb_id for row in unreviewed}
    reviewed, _ = select_manifest(by_language, reviewed_ambiguous={first.imdb_id: first.wikidata_id})
    assert first.imdb_id in {row.imdb_id for row in reviewed}


def test_article_section_audit_counts_nested_plot_and_alternate_headings() -> None:
    axes = section_coverage({"plot/theatrical-release-1975", "production/filming",
                             "release-reception/critical-reviews", "influence"})
    assert axes == {"plot": True, "production": True,
                    "reception": True, "legacy": True}
    assert section_coverage({"lead", "tmdb.overview"})["plot"] is False


def test_source_metadata_audit_reports_conflicts_without_promoting_either_source() -> None:
    conflicts = compare_source_metadata("A Film", "Q123", "te", {2008}, {"2009"}, {"ta"})
    assert [item["field"] for item in conflicts] == ["primary_release_year", "original_language"]
    assert compare_source_metadata("A Film", "Q123", "mul", {2008}, {"2009"}, {"ta"}) == conflicts[:1]
    assert compare_source_metadata("A Film", "Q123", "te", {2008}, {"2008"}, {"te"}) == []


def test_intake_uses_exact_imdb_identity_and_local_prefix_suggestions(tmp_path) -> None:
    dataset, _ = _mini_dataset(tmp_path)
    assert dataset.suggest_titles("a fi")[0]["tconst"] == "tt0000001"
    assert imdb_id_from_input("tt0000001") == "tt0000001"
    assert imdb_id_from_input("https://www.imdb.com/title/tt0000001/?ref_=example") == "tt0000001"
    assert imdb_id_from_input("https://example.com/title/tt0000001/") is None
    assert imdb_id_from_input("http://www.imdb.com/title/tt0000001/") is None


def test_wikidata_imdb_discovery_retains_ambiguous_qids() -> None:
    assert '"tt0000001"' in imdb_qid_query(["tt0000001"])
    payload = {"results": {"bindings": [
        {"imdb": {"value": "tt0000001"}, "item": {"value": "http://www.wikidata.org/entity/Q1"}},
        {"imdb": {"value": "tt0000001"}, "item": {"value": "http://www.wikidata.org/entity/Q2"}},
    ]}}
    assert qids_by_imdb(payload) == {"tt0000001": ["Q1", "Q2"]}


@pytest.mark.integration
def test_movie_snapshot_to_operational_assertions_is_idempotent(tmp_path) -> None:
    dataset, bundle = _mini_dataset(tmp_path)
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(code="en", display_name="English", script="Latin", enabled=True, status="live"))
        entity = CanonicalEntity(entity_kind="film", canonical_label="A Film")
        db.add(entity)
        db.flush()
        film = Film(entity_id=entity.id, canonical_title="A Film", original_language_code="en")
        db.add(film)
        source, policy = source_registration(db, IMDB_SOURCE)
        db.commit()
        run = start_run(db, source, policy, adapter="imdb_local_tsv", requested=1, manifest="fixture")
        args = dict(
            run=run, source=source, external_id="tt0000001", film=film,
            bundle=bundle, facts=imdb_facts(bundle),
            canonical_url="https://www.imdb.com/title/tt0000001/",
            revision="fixture-v1", snapshot_root=tmp_path / "snapshots",
        )
        first = persist_movie_bundle(db, **args)
        prior = Assertion(
            subject_entity_id=entity.id, predicate="imdb_identifier",
            value_json={"value": "tt9999999"}, qualifiers={},
            assertion_kind="source_fact", source_id=source.id,
            source_reference="https://example.org/old-id",
            derivation_version="fixture", review_status="resolved",
        )
        db.add(prior)
        db.flush()
        correction = MovieSeed("A Film", 2008, imdb_id="tt0000001",
                               entity_id=entity.id, replaces_imdb_id="tt9999999")
        assert retract_replaced_identifier(db, dataset, correction, film, "tt0000001") == 1
        assert prior.review_status == "retracted"
        raw_credit = SourceAssertion(
            source_snapshot_id=db.scalar(select(SourceSnapshot.id)),
            statement_locator="principals[0]", source_property="principals",
            raw_subject={"external_id": "tt0000001"},
            raw_value={"name": "Actor One"}, raw_qualifiers={},
            extractor_version="movie-source-facts-v1",
        )
        db.add(raw_credit)
        db.flush()
        older_projection = Assertion(
            subject_entity_id=entity.id, predicate="cast",
            value_json={"name": "Actor One"}, qualifiers={},
            assertion_kind="source_fact", source_id=source.id,
            source_reference=args["canonical_url"],
            derivation_version="movie-source-facts-v1", review_status="resolved",
        )
        db.add(older_projection)
        db.add(AssertionEvidence(
            assertion=older_projection, source_assertion_id=raw_credit.id,
            evidence_type="source_assertion", reference=args["canonical_url"],
        ))
        saved_snapshot = db.scalar(select(SourceSnapshot))
        original_storage_uri = saved_snapshot.storage_uri
        saved_snapshot.storage_uri = "file:///private/tmp/obsolete-cinegraph-snapshot.json"
        db.commit()
        second = persist_movie_bundle(db, **args)
        db.commit()
        assert first["snapshot_created"] == 1
        assert first["source_assertions"] > 0
        assert first["assertions_projected"] > 0
        assert second["snapshot_created"] == 0
        assert second["source_assertions"] == 0
        assert second["assertions_projected"] == 0
        assert older_projection.review_status == "retracted"
        assert saved_snapshot.storage_uri == original_storage_uri
        assert db.query(SourceSnapshot).count() == 1
        assert db.query(AssertionEvidence).count() == db.query(SourceAssertion).count()
        assert db.scalar(select(Assertion).where(Assertion.predicate == "cast")).value_json["characters"] == ["The Hero"]
        assert retract_replaced_identifier(db, dataset, correction, film, "tt0000001") == 0
        assert json.loads(Path(tmp_path / "index" / "basics.sparse.json").read_text())["sha256"]
        tmdb_source, tmdb_policy = source_registration(db, TMDB_SOURCE)
        tmdb_run = start_run(db, tmdb_source, tmdb_policy, adapter="fixture", requested=1, manifest="fixture")
        tmdb_bundle = {"id": 42, "title": "A Film", "external_ids": {"imdb_id": "tt0000001"},
                       "overview": "An attributable synopsis."}
        persist_movie_bundle(db, run=tmdb_run, source=tmdb_source, external_id="42", film=film,
                             bundle=tmdb_bundle, facts=tmdb_facts(tmdb_bundle),
                             canonical_url="https://www.themoviedb.org/movie/42", revision=None,
                             snapshot_root=tmp_path / "snapshots")
        db.commit()
        assert cached_tmdb_id(db, film, "tt0000001") == "42"
        assert cached_tmdb_id(db, film, "tt9999999") is None


@pytest.mark.integration
def test_collection_audit_flags_missing_character_credit() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(code="en", display_name="English", script="Latin",
                               enabled=True, status="active"))
        entity = CanonicalEntity(entity_kind="film", canonical_label="A Film", wikidata_id="Q123")
        db.add(entity)
        db.flush()
        db.add(Film(entity_id=entity.id, canonical_title="A Film",
                    original_language_code="en"))
        db.add(ReferenceCollection(code="fixture", title="Fixture", description="Audit fixture",
                                   language_code="en", selection_method="fixture",
                                   selection_version="v1"))
        db.add(ReferenceCollectionMembership(collection_code="fixture", entity_id=entity.id,
                                             source_reference="https://example.org/fixture"))
        db.commit()
        report = audit_collection(db, "fixture")
        assert report["coverage"].get("with_any_character_credit", 0) == 0
        assert "no_character_credit" in report["gaps"][0]["issues"]


@pytest.mark.integration
def test_intake_job_claim_is_durable_and_not_double_claimed() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(MovieIntakeJob(imdb_id="tt0000001", title="A Film", year=2008,
                              status="queued", stage="queued", attempts=0))
        db.commit()
        claimed = claim_next(db)
        assert claimed is not None
        assert claimed.status == "running"
        assert claimed.stage == "imdb_tmdb"
        assert claimed.attempts == 1
        assert claim_next(db) is None


@pytest.mark.integration
def test_intake_batch_validates_all_movies_and_deduplicates(tmp_path) -> None:
    dataset, _ = _mini_dataset(tmp_path)
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with pytest.raises(ValueError, match="not a local IMDb movie"):
            enqueue_films(db, dataset, ["tt0000001", "tt9999999"])
        assert db.scalar(select(MovieIntakeJob.id)) is None
        first = enqueue_films(db, dataset, ["tt0000001", "https://www.imdb.com/title/tt0000001/"])
        second = enqueue_films(db, dataset, ["tt0000001"])
        assert len(first) == len(second) == 1
        assert first[0].id == second[0].id
        assert first[0].title == "A Film"


@pytest.mark.integration
def test_enwiki_manifest_uses_retained_wikidata_sitelink_only(tmp_path) -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = DataSource(name="Wikidata", url="https://www.wikidata.org/",
                            source_type="structured_metadata", license="CC0 1.0",
                            rights_status="attributed_reuse")
        db.add(source)
        db.flush()
        policy = wikidata_api_policy(db, source)
        run = start_run(db, source, policy, adapter="fixture", requested=1, manifest="fixture")
        item = source_object(db, source=source, external_id="Q123",
                             object_kind="wikibase_item", canonical_url="https://www.wikidata.org/wiki/Q123")
        snapshot(db, item=item, run=run,
                 payload=json.dumps({"id": "Q123", "sitelinks": {"enwiki": {"title": "A Film"}}}).encode(),
                 source_revision="1", canonical_url=item.canonical_url,
                 license="CC0 1.0", attribution_url=item.canonical_url,
                 storage_root=tmp_path / "raw")
        db.commit()
        selection = tmp_path / "films.jsonl"
        selection.write_text(json.dumps({"title": "A Film", "year": 2008,
                                         "wikidata_id": "Q123"}) + "\n", encoding="utf-8")
        result = build_manifests(db, selection, tmp_path / "jobs", chunk_size=1)
        assert result["with_enwiki_sitelink"] == 1
        job = json.loads(Path(result["revision_job_manifests"][0]).read_text())
        assert job["entries"][0]["wikipedia_title"] == "A Film"
        assert job["entries"][0]["verified_wikidata_sitelink"] is True
        assert [path.name for path in listed_chunk_paths(tmp_path / "jobs")] == ["enwiki_chunk_0001.json"]


@pytest.mark.integration
def test_language_reconciliation_requires_reviewed_raw_linked_values(tmp_path) -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(code="te", display_name="Telugu", script="Telugu",
                               enabled=False, status="planned"))
        film_entity = CanonicalEntity(entity_kind="film", canonical_label="A Film", wikidata_id="Q123")
        db.add(film_entity)
        db.flush()
        film = Film(entity_id=film_entity.id, canonical_title="A Film",
                    original_language_code="te", review_status="review_required")
        db.add(film)
        source = DataSource(name="Wikidata", url="https://www.wikidata.org/",
                            source_type="structured_metadata", license="CC0 1.0",
                            rights_status="attributed_reuse")
        db.add(source)
        db.flush()
        policy = wikidata_api_policy(db, source)
        run = start_run(db, source, policy, adapter="fixture", requested=1, manifest="fixture")
        item = source_object(db, source=source, external_id="Q123",
                             object_kind="wikibase_item", canonical_url="https://www.wikidata.org/wiki/Q123")
        saved, _ = snapshot(db, item=item, run=run, payload=b'{"id":"Q123"}',
                            source_revision="1", canonical_url=item.canonical_url,
                            license="CC0 1.0", attribution_url=item.canonical_url,
                            storage_root=tmp_path / "raw")
        for index, qid in enumerate(("Q8097", "Q36236")):
            raw = SourceAssertion(source_snapshot_id=saved.id, statement_locator=f"P364/{index}",
                                  source_property="P364", raw_subject={"id": "Q123"},
                                  raw_value={"id": qid}, raw_qualifiers={}, extractor_version="fixture")
            db.add(raw)
            db.flush()
            assertion = Assertion(subject_entity_id=film_entity.id, predicate="original_language",
                                  value_json={"wikidata_id": qid}, qualifiers={},
                                  assertion_kind="source_fact", source_id=source.id,
                                  source_reference=item.canonical_url,
                                  derivation_version="fixture", review_status="resolved")
            db.add(assertion)
            db.flush()
            db.add(AssertionEvidence(assertion_id=assertion.id, source_assertion_id=raw.id,
                                     evidence_type="source_assertion", reference=item.canonical_url))
        db.commit()
        assert reconcile_language(db, "Q123", apply=False)["projected_language"] == "mul"
        assert film.original_language_code == "te"
        assert reconcile_language(db, "Q123", apply=True)["status"] == "updated"
        db.commit()
        assert film.original_language_code == "mul"
        film.original_language_code = "te"
        film.review_status = "published"
        db.commit()
        assert reconcile_language(db, "Q123", apply=True)["status"] == "review_required"
        assert film.original_language_code == "te"
        assert reconcile_language(db, "Q123", apply=True,
                                  approved_projected_language="ml")["status"] == "review_required"
        assert reconcile_language(db, "Q123", apply=True,
                                  approved_projected_language="mul")["status"] == "updated"
        dataset, _ = _mini_dataset(tmp_path)
        for index, imdb_id in enumerate(("tt0000001", "tt9999999")):
            raw = SourceAssertion(source_snapshot_id=saved.id, statement_locator=f"P345/{index}",
                                  source_property="P345", raw_subject={"id": "Q123"},
                                  raw_value={"value": imdb_id}, raw_qualifiers={}, extractor_version="fixture")
            db.add(raw)
            db.flush()
            assertion = Assertion(subject_entity_id=film_entity.id, predicate="imdb_identifier",
                                  value_json={"value": imdb_id}, qualifiers={},
                                  assertion_kind="source_fact", source_id=source.id,
                                  source_reference=item.canonical_url,
                                  derivation_version="fixture", review_status="resolved")
            db.add(assertion)
            db.flush()
            db.add(AssertionEvidence(assertion_id=assertion.id, source_assertion_id=raw.id,
                                     evidence_type="source_assertion", reference=item.canonical_url))
        db.commit()
        seed = MovieSeed("A Film", 2008, imdb_id="tt0000001", wikidata_id="Q123")
        assert review_wikidata_imdb_id(db, dataset, seed, apply=False)["status"] == "ready"
        assert review_wikidata_imdb_id(db, dataset, seed, apply=True)["status"] == "quarantined"
        db.commit()
        statuses = {row.value_json["value"]: row.review_status for row in db.scalars(
            select(Assertion).where(Assertion.predicate == "imdb_identifier"))}
        assert statuses == {"tt0000001": "resolved", "tt9999999": "review_required"}
