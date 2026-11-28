"""Read-only question probes against the inactive local 4B pilot, not serving."""
from dataclasses import asdict
import json
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal
from app.models import Film
from app.services.hybrid_evidence_retrieval import NarrativeRetrievalMethod, retrieve_narrative_candidates
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
from app.services.retrieval_scope import resolve_retrieval_scope
from build_inactive_recovery_pilot import COLLECTION, DIGEST


def main():
    output=Path("data/evaluation/recovery-inactive-live-db-probes-v1.json")
    if output.exists():
        raise FileExistsError(output)
    probes=[
        (("Q23781155","Q47703"),"how do these follow the conflicts between family or close people when fighting injustice"),
        (("Q788822","Q104905"),"How does each film make an artificial companion expose human loneliness?"),
    ]
    client=OllamaEmbeddingClient(base_url="http://host.docker.internal:11434")
    profile=OllamaEmbeddingProfile(model="qwen3-embedding:4b",expected_model_digest=DIGEST)
    results=[]
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        scope=resolve_retrieval_scope(db,collection_code=COLLECTION,model_name=profile.model)
        if scope.index_run is None:
            raise ValueError("inactive_index_missing")
        for qids,question in probes:
            vector=client.embed([profile.query_input(question)],profile=profile)[0]
            sides=[]
            for qid in qids:
                film=db.query(Film).filter_by(wikidata_id=qid).one()
                methods={}
                for method in NarrativeRetrievalMethod:
                    result=retrieve_narrative_candidates(db,subject_entity_id=film.entity_id,
                        question_id="story.plot_character_structure",question_text=question,
                        method=method,scope=scope,query_vector=vector,restrict_sections=False,limit=10)
                    methods[method.value]=asdict(result)
                sides.append({"qid":qid,"methods":methods})
            results.append({"question":question,"sides":sides})
        report={"index_run_id":str(scope.index_run.id),"collection":COLLECTION,
            "probes":results,"semantic_review":"pending","active":False,
            "caution":"Read-only development probes; not generated answers or a quality score."}
    with output.open("x") as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2)
    print(json.dumps({"output":str(output),"questions":len(results),"index_run_id":report["index_run_id"]}))


if __name__=="__main__":
    main()
