"""One-case local MLX batching diagnostic; compares actual scores, not just ranks."""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

from app.services.pair_mlx_reranker_trial import PREFIX, SUFFIX, final_yes_no_logits, mlx_runtime_limits
from app.services.pair_reranker_trial import INSTRUCTION, require_disk_headroom, reranker_document, reranker_query


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("capture","model","output"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--case-id",required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root/"data"/"evaluation") or args.output.exists():
        raise ValueError("Output must be new and within data/evaluation")
    require_disk_headroom(args.output)
    capture=json.loads(args.capture.read_text())
    matches=[c for c in capture["cases"] if c["case_id"]==args.case_id]
    if len(matches)!=1: raise ValueError("Expected one exact case")
    import mlx.core as mx
    from mlx_lm import load
    limits=mlx_runtime_limits(); mx.set_memory_limit(limits["memory_limit_bytes"]); mx.set_cache_limit(limits["cache_limit_bytes"])
    mx.reset_peak_memory()
    model, tokenizer=load(str(args.model)); hf=getattr(tokenizer,"_tokenizer",tokenizer)
    yes,no=hf.convert_tokens_to_ids("yes"),hf.convert_tokens_to_ids("no")
    prefix=hf.encode(PREFIX,add_special_tokens=False); suffix=hf.encode(SUFFIX,add_special_tokens=False)
    case=matches[0]; inputs=[]
    for side,title in zip(("first","second"),case["titles"],strict=True):
        query=reranker_query(case["question"],title)
        for item in case[side+"_pool"]:
            doc=reranker_document(item["content"],film_title=title,section_title=item["section_title"])
            ids=prefix+hf.encode(f"<Instruct>: {INSTRUCTION}\n<Query>: {query}\n<Document>: {doc}",add_special_tokens=False)+suffix
            if len(ids)>8192: raise ValueError("Input exceeds token budget")
            inputs.append((side,item["chunk_id"],ids))
    def scalar(ids):
        logits=final_yes_no_logits(model,mx,ids); value=logits[0,yes]-logits[0,no]; mx.eval(value)
        return float(value)
    start=perf_counter(); single=[scalar(ids) for _,_,ids in inputs]; single_s=perf_counter()-start
    mx.clear_cache(); start=perf_counter(); batched=[]
    for offset in range(0,len(inputs),2):
        require_disk_headroom(args.output)
        batch=inputs[offset:offset+2]; length=max(len(x[2]) for x in batch)
        # Right padding cannot affect earlier positions under causal attention.
        tokens=mx.array([ids+[hf.eos_token_id]*(length-len(ids)) for _,_,ids in batch])
        hidden=model.model(tokens)
        last=mx.stack([hidden[i,len(ids)-1,:] for i,(_,_,ids) in enumerate(batch)])
        logits=model.model.embed_tokens.as_linear(last) if model.args.tie_word_embeddings else model.lm_head(last)
        scores=logits[:,yes]-logits[:,no]; mx.eval(scores); batched.extend(float(x) for x in scores.tolist())
        del tokens,hidden,last,logits,scores
        mx.clear_cache()
    batch_s=perf_counter()-start
    result={"case_id":args.case_id,"capture_sha256":hashlib.sha256(args.capture.read_bytes()).hexdigest(),
        "single_seconds":single_s,"batch_seconds":batch_s,"batch_size":2,"peak_memory_bytes":mx.get_peak_memory(),
        "max_abs_delta":max(abs(a-b) for a,b in zip(single,batched,strict=True)),
        "scores":[{"side":side,"chunk_id":cid,"single":a,"batched":b} for (side,cid,_),a,b in zip(inputs,single,batched,strict=True)]}
    with args.output.open('x') as h: json.dump(result,h,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='scores'}))


if __name__=='__main__': main()
