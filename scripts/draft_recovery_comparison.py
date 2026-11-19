"""Explicit local-only grounded draft from retained selected evidence."""
import argparse
import json
from pathlib import Path
import shutil
import time
import httpx
from app.services.ollama_embeddings import local_model_digest
from app.services.rag_grounded_trial import SYSTEM, answer_schema, validate_answer


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", choices=("qwen3:4b", "qwen3:8b"), required=True)
    p.add_argument("--digest", required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if shutil.disk_usage(Path.cwd()).free < 6*1024**3:
        raise RuntimeError("disk_reserve")
    url = "http://127.0.0.1:11435"
    if local_model_digest(url, args.model) != args.digest:
        raise ValueError("model_digest_mismatch")
    packet = json.loads(args.evidence.read_text())
    if len(packet["cases"]) != 1:
        raise ValueError("single_diagnostic_case_required")
    case = packet["cases"][0]
    entries = []
    for prefix, side in zip(("A","B"), case["sides"], strict=True):
        selected = side["selected"]
        # Readable, bounded development packing: retain top context and up to
        # two narrative leads from the already selected set, not new retrieval.
        plot = [r for r in selected if r["section_title"].split("/")[0].strip().lower() == "plot"]
        chosen, seen = [], set()
        for row in [*plot[:2], *selected]:
            if row["chunk_id"] in seen:
                continue
            seen.add(row["chunk_id"])
            chosen.append(row)
            if len(chosen) == 3:
                break
        for i, row in enumerate(chosen, 1):
            entries.append({"ref": prefix+str(i), "content": row["text"],
                "film_qid": side["film_qid"], "source_snapshot_id": row["source_snapshot_id"],
                "chunk_id": row["chunk_id"], "start": row["start"], "end": row["end"]})
    pack = {"question": case["question"], "entries": entries}
    schema = answer_schema(pack)
    user = json.dumps({"question": case["question"], "evidence": entries}, ensure_ascii=False)
    context = 16384
    output = 1536
    # Conservative byte upper bound, not an assumed character/token ratio.
    if len((SYSTEM+user+json.dumps(schema)).encode()) + output + 1024 > context:
        raise ValueError("evidence_exceeds_context_budget")
    start = time.monotonic()
    response = httpx.post(url+"/api/chat", timeout=300, json={
        "model": args.model, "stream": False, "think": False, "format": schema,
        "messages": [{"role":"system","content":SYSTEM}, {"role":"user","content":user}],
        "options":{"temperature":0, "seed":42, "num_ctx":context, "num_predict":output},
        "keep_alive":0})
    response.raise_for_status()
    payload = response.json()
    raw = payload["message"]["content"]
    errors = []
    try:
        validate_answer(raw, pack)
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    if local_model_digest(url, args.model) != args.digest:
        errors.append("model_changed_during_run")
    result = {"model":args.model,"digest":args.digest,"seconds":time.monotonic()-start,
        "context":context,"max_output_tokens":output,"pack":pack,"raw":raw,
        "structural_errors":errors,"semantic_review":"pending","quality_score":None,
        "done_reason":payload.get("done_reason"),"eval_count":payload.get("eval_count"),
        "prompt_eval_count":payload.get("prompt_eval_count")}
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("pack","raw")}))


if __name__ == "__main__":
    main()
