"""Read-only question probes against the inactive local 4B pilot, not serving."""
from dataclasses import asdict
import argparse
import json
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal
from app.models import Film
from app.services.hybrid_evidence_retrieval import NarrativeRetrievalMethod, retrieve_narrative_candidates
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
from app.services.retrieval_scope import resolve_retrieval_scope
from build_inactive_recovery_pilot import COLLECTION, DIGEST
from evaluate_question_section_reserve import requested_section


def focused_question(question):
    """Development hypothesis: make the requested evidence type explicit.

    No film names, plot events, gold annotations or answer text are injected.
    This changes query text only; model instruction and document vectors stay fixed.
    """
    section=requested_section(question)
    focus={"production":"Filmmaking decisions and techniques",
           "reception":"Attributed critical responses and disagreements",
           "plot":"Character actions, decisions, relationships and consequences"}.get(section)
    return f"{focus}. Answer this specific question: {question}" if focus else question


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development",action="store_true")
    parser.add_argument("--output",type=Path,default=Path("data/evaluation/recovery-inactive-live-db-probes-v1.json"))
    args=parser.parse_args()
    output=args.output
    area=Path("data/evaluation").resolve()
    if not output.resolve().is_relative_to(area):
        raise ValueError("local_evaluation_output_required")
    if output.exists():
        raise FileExistsError(output)
    probes=[
        (("Q23781155","Q47703"),"how do these follow the conflicts between family or close people when fighting injustice"),
        (("Q788822","Q104905"),"How does each film make an artificial companion expose human loneliness?"),
    ]
    corpus=json.loads((area/"recovery-ten-film-current-v1.json").read_text())
    if args.development:
        probes=[(c["film_qids"],c["question"]) for c in corpus["cases"]]
    client=OllamaEmbeddingClient(base_url="http://host.docker.internal:11434")
    profile=OllamaEmbeddingProfile(model="qwen3-embedding:4b",expected_model_digest=DIGEST)
    results=[]
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        scope=resolve_retrieval_scope(db,collection_code=COLLECTION,model_name=profile.model)
        if scope.index_run is None:
            raise ValueError("inactive_index_missing")
        for n,(qids,question) in enumerate(probes):
            vector=client.embed([profile.query_input(question)],profile=profile)[0]
            focused=focused_question(question)
            focused_vector=client.embed([profile.query_input(focused)],profile=profile)[0] if focused!=question else vector
            sides=[]
            for qid in qids:
                film=db.query(Film).filter_by(wikidata_id=qid).one()
                methods={}
                for method in NarrativeRetrievalMethod:
                    result=retrieve_narrative_candidates(db,subject_entity_id=film.entity_id,
                        question_id="story.plot_character_structure",question_text=question,
                        method=method,scope=scope,query_vector=vector,restrict_sections=False,limit=20)
                    methods[method.value]=asdict(result)
                methods["focused_semantic"]=asdict(retrieve_narrative_candidates(db,
                    subject_entity_id=film.entity_id,question_id="story.plot_character_structure",
                    question_text=focused,method=NarrativeRetrievalMethod.SEMANTIC,scope=scope,
                    query_vector=focused_vector,restrict_sections=False,limit=20))
                sides.append({"qid":qid,"methods":methods})
            results.append({"case_id":corpus["cases"][n]["case_id"] if args.development else f"diagnostic-{n+1}",
                "question":question,"focused_query":focused,"sides":sides})
            print(f"Completed {n+1}/{len(probes)}",flush=True)
        report={"index_run_id":str(scope.index_run.id),"collection":COLLECTION,
            "corpus_fingerprint":corpus["fingerprint"],"development":args.development,
            "probes":results,"semantic_review":"pending","active":False,
            "caution":"Read-only development probes; not generated answers or a quality score."}
    with output.open("x") as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2)
    print(json.dumps({"output":str(output),"questions":len(results),"index_run_id":report["index_run_id"]}))


if __name__=="__main__":
    main()
