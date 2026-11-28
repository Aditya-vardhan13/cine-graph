"""Offline same-packet prefix-cache parity and timing diagnostic on MLX."""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

from app.services.pair_mlx_reranker_trial import PREFIX, SUFFIX, final_yes_no_logits, mlx_runtime_limits
from app.services.pair_reranker_trial import INSTRUCTION, require_disk_headroom, reranker_document, reranker_query


def common_prefix(sequences):
    if not sequences or any(not s for s in sequences):
        raise ValueError("nonempty_sequences_required")
    end=min(map(len,sequences))
    for i in range(end):
        if any(s[i]!=sequences[0][i] for s in sequences[1:]):
            return sequences[0][:i]
    return sequences[0][:end]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ("capture","model","output"):
        p.add_argument("--"+flag,type=Path,required=True)
    p.add_argument("--case-id",required=True)
    args=p.parse_args()
    area=Path("data/evaluation").resolve()
    if not args.capture.resolve().is_relative_to(area) or not args.output.resolve().is_relative_to(area) or args.output.exists():
        raise ValueError("new_local_evaluation_output_required")
    if not args.model.resolve().is_relative_to(Path("data/models").resolve()):
        raise ValueError("project_local_model_required")
    require_disk_headroom(args.output)
    capture=json.loads(args.capture.read_text())
    cases=[c for c in capture["cases"] if c["case_id"]==args.case_id]
    if len(cases)!=1: raise ValueError("one_exact_case_required")
    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.models.cache import make_prompt_cache
    limits=mlx_runtime_limits(); mx.set_memory_limit(limits["memory_limit_bytes"]); mx.set_cache_limit(limits["cache_limit_bytes"])
    mx.reset_peak_memory()
    model,tokenizer=load(str(args.model),tokenizer_config={"trust_remote_code":False})
    hf=getattr(tokenizer,"_tokenizer",tokenizer)
    yes,no=hf.convert_tokens_to_ids("yes"),hf.convert_tokens_to_ids("no")
    prefix=hf.encode(PREFIX,add_special_tokens=False); suffix=hf.encode(SUFFIX,add_special_tokens=False)
    case=cases[0]; results=[]
    for side,title in zip(("first","second"),case["titles"],strict=True):
        query=reranker_query(case["question"],title)
        pool=case[side+"_pool"]
        sequences=[]
        for row in pool:
            doc=reranker_document(row["content"],film_title=title,section_title=row["section_title"])
            ids=prefix+hf.encode(f"<Instruct>: {INSTRUCTION}\n<Query>: {query}\n<Document>: {doc}",add_special_tokens=False)+suffix
            if len(ids)>8192: raise ValueError("input_exceeds_limit")
            sequences.append(ids)
        shared=common_prefix(sequences)
        if not shared or any(len(ids)==len(shared) for ids in sequences): raise ValueError("invalid_shared_prefix")
        scores=[]; start=perf_counter()
        for ids in sequences:
            require_disk_headroom(args.output)
            logits=final_yes_no_logits(model,mx,ids); score=logits[0,yes]-logits[0,no]; mx.eval(score)
            scores.append(float(score)); del logits,score
        baseline=perf_counter()-start; mx.clear_cache(); start=perf_counter()
        cached=make_prompt_cache(model)
        prefix_hidden=model.model(mx.array([shared]),cache=cached)
        mx.eval(prefix_hidden,*[v for c in cached for v in c.state]); del prefix_hidden
        cached_scores=[]
        for ids in sequences:
            require_disk_headroom(args.output)
            # New cache objects share only immutable prefix arrays; model writes
            # suffixes into fresh buffers. No candidate state is reused.
            current=[type(c).from_state(c.state,c.meta_state) for c in cached]
            hidden=model.model(mx.array([ids[len(shared):]]),cache=current)[:,-1:,:]
            logits=model.model.embed_tokens.as_linear(hidden) if model.args.tie_word_embeddings else model.lm_head(hidden)
            score=logits[0,-1,yes]-logits[0,-1,no]; mx.eval(score)
            cached_scores.append(float(score)); del current,hidden,logits,score
        elapsed=perf_counter()-start
        baseline_order=sorted(range(len(scores)),key=lambda i:(-scores[i],i))
        cached_order=sorted(range(len(scores)),key=lambda i:(-cached_scores[i],i))
        results.append({"side":side,"candidates":len(pool),"shared_prefix_tokens":len(shared),
            "baseline_seconds":baseline,"cached_seconds_including_prefill":elapsed,
            "max_abs_delta":max(abs(a-b) for a,b in zip(scores,cached_scores,strict=True)),
            "top5_baseline":[pool[i]["chunk_id"] for i in baseline_order[:5]],
            "top5_cached":[pool[i]["chunk_id"] for i in cached_order[:5]],
            "scores":[{"chunk_id":r["chunk_id"],"baseline":a,"cached":b} for r,a,b in zip(pool,scores,cached_scores,strict=True)]})
        print(json.dumps({k:v for k,v in results[-1].items() if k!="scores"}),flush=True)
        del cached
        mx.clear_cache()
    with (args.model/"model.safetensors").open("rb") as h: model_hash=hashlib.file_digest(h,"sha256").hexdigest()
    report={"case_id":args.case_id,"capture_sha256":hashlib.sha256(args.capture.read_bytes()).hexdigest(),
        "model_sha256":model_hash,"runtime_limits":limits,"peak_memory_bytes":mx.get_peak_memory(),"sides":results,
        "caution":"One offline diagnostic; score parity does not prove relevance or production performance."}
    with args.output.open("x") as h: json.dump(report,h,indent=2)


if __name__=="__main__": main()
