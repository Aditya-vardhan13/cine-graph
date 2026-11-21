"""Offline, local-only evidence observations followed by a tentative comparison."""
import argparse
import json
from pathlib import Path
import shutil
import time

import httpx
from app.services.corpus_build_manifest import canonical_digest
from app.services.ollama_embeddings import local_model_digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ("baseline","output"):
        p.add_argument("--"+flag,type=Path,required=True)
    p.add_argument("--model",choices=("qwen3:4b","qwen3:8b"),required=True)
    p.add_argument("--digest",required=True)
    p.add_argument("--selected",type=Path,required=True,help="Original selected evidence with section labels")
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]/"data"/"evaluation"
    if any(not x.resolve().is_relative_to(root) for x in (args.baseline,args.selected,args.output)) or args.output.exists():
        raise ValueError("Use a new project-local evaluation output")
    if shutil.disk_usage(root).free < 6*1024**3: raise RuntimeError("disk_reserve")
    url="http://127.0.0.1:11435"
    if local_model_digest(url,args.model)!=args.digest: raise ValueError("model_digest_mismatch")
    baseline=json.loads(args.baseline.read_text()); pack=baseline["pack"]
    selected=json.loads(args.selected.read_text())
    rows={r["chunk_id"]:r for case in selected["cases"] for side in case["sides"] for r in side["selected"]}
    for entry in pack["entries"]:
        row=rows[entry["chunk_id"]]
        if (row["text"]!=entry["content"] or row["film_qid"]!=entry["film_qid"]
            or row["source_snapshot_id"]!=entry["source_snapshot_id"]):
            raise ValueError("selected_source_mismatch")
        entry["section_title"]=row["section_title"]
    schema={"type":"object","properties":{"participants":{"type":"string"},"action":{"type":"string"},
        "source_type":{"type":"string","enum":["plot","filmmaker_statement","criticism","other"]},
        "ref":{"type":"string"},"quote":{"type":"string"},"limit":{"type":"string"}},
        "required":["participants","action","source_type","ref","quote","limit"],"additionalProperties":False}
    calls=[]
    def chat(system,user,format_schema):
        if shutil.disk_usage(root).free < 6*1024**3: raise RuntimeError("disk_reserve")
        start=time.monotonic()
        response=httpx.post(url+"/api/chat",timeout=300,json={"model":args.model,"stream":False,
            "think":False,"format":format_schema,"keep_alive":"5m",
            "messages":[{"role":"system","content":system},{"role":"user","content":json.dumps(user,ensure_ascii=False)}],
            "options":{"temperature":0,"seed":42,"num_ctx":8192,"num_predict":400}})
        response.raise_for_status(); payload=response.json()
        calls.append({"seconds":time.monotonic()-start,"prompt_tokens":payload.get("prompt_eval_count"),
            "output_tokens":payload.get("eval_count"),"done_reason":payload.get("done_reason")})
        return json.loads(payload["message"]["content"])
    observations=[]; errors=[]
    for prefix in ("A","B"):
        entries=[e for e in pack["entries"] if e["ref"].startswith(prefix)]
        result=chat("Consider only this film and only the supplied evidence. Name the specific participants and their types if stated, such as human, operating system, robot, or unknown. Describe one concrete action by named participants that the quote directly states. Prefer plot evidence for actions. Do not generalize from characters to all companions, invent motivations, or claim a directorial statement is a plot event. Copy one exact contiguous quotation and identify its source type. If a requested detail is not in evidence, state that in limit.",
            {"question":pack["question"],"evidence":entries},schema)
        refs={e["ref"]:e["content"] for e in entries}
        if result.get("ref") not in refs or not result.get("quote") or result["quote"] not in refs[result["ref"]]:
            errors.append(prefix+":invalid_quote")
        observations.append(result)
    synthesis=None
    if not errors:
        compare_schema={"type":"object","properties":{"comparison":{"type":"string"},"limit":{"type":"string"}},
            "required":["comparison","limit"],"additionalProperties":False}
        synthesis=chat("Compare only the two observations. Name each film's participants and types if stated, and the actual action in each. Explain a difference only if the observations support it. Do not generalize about all companions, confuse a filmmaker statement with an event, infer motives, or force the same premise. If observations cannot answer part of the question, state the gap.",
            {"question":pack["question"],"observations":observations},compare_schema)
    if local_model_digest(url,args.model)!=args.digest: errors.append("model_changed_during_run")
    result={"model":args.model,"digest":args.digest,"prompt_version":"participant-action-v3-section-labels",
        "selected_sha256":canonical_digest(selected),"pack_sha256":canonical_digest(pack),"pack":pack,
        "observations":observations,"synthesis":synthesis,"structural_errors":errors,"calls":calls,
        "semantic_review":"pending","caution":"Exact quote checks do not establish entailment. Offline only."}
    with args.output.open("x") as h: json.dump(result,h,ensure_ascii=False,indent=2); h.write("\n")
    print(json.dumps({"structural_errors":errors,"calls":calls,"semantic_review":"pending"}))


if __name__=="__main__": main()
