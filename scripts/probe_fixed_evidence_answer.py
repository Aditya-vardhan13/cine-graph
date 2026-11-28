"""Offline fixed-source answer probe for the user's Endgame/Godfather question.

This curated packet is an oracle diagnostic, not measured retrieval output.
No answer is exposed through the product.
"""
import hashlib
import argparse
import json
import re
from pathlib import Path
import shutil
import time

import httpx
from app.services.corpus_build_manifest import canonical_digest
from app.services.ollama_embeddings import local_model_digest
from app.services.rag_grounded_trial import SYSTEM, answer_schema, validate_answer, messages, resolve_span_answer, quote_spans


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--span-ids',action='store_true',help='Select sentence IDs instead of copying quotes')
    args=parser.parse_args()
    area=Path('data/evaluation')
    corpus=json.loads((area/'recovery-ten-film-current-v1.json').read_text())
    if canonical_digest({k:v for k,v in corpus.items() if k!='fingerprint'})!=corpus['fingerprint']:
        raise ValueError('corpus_fingerprint_mismatch')
    output=area/('recovery-original-fixed-evidence-answer4b-span-v1.json' if args.span_ids else 'recovery-original-fixed-evidence-answer4b-v1.json')
    if output.exists(): raise FileExistsError(output)
    docs={d['chunk_id']:d for d in corpus['documents']}
    selected=[('A1','e0762d6e-3bbe-44ab-a389-008c8d859ab9','Q23781155'),
              ('B1','d2a94769-a929-4170-8457-88d562cb525b','Q47703'),
              ('B2','dbf4ffb6-1a7a-4c29-b216-d19952d37b88','Q47703')]
    entries=[]
    for ref,pid,qid in selected:
        d=docs[pid]
        if d['film_qid']!=qid or hashlib.sha256(d['content'].encode()).hexdigest()!=d['content_sha256']:
            raise ValueError('source_passage_mismatch')
        entries.append({'ref':ref,'film_qid':qid,'film_title':d['film_title'],'section_title':d['section_title'],
            'source_snapshot_id':d['source_snapshot_id'],'chunk_id':pid,'content':d['content']})
        if args.span_ids:
            # Exact character offsets; never rewrite source text or treat this
            # simple sentence split as a semantic support judgment.
            boundaries=[0]+[m.end() for m in re.finditer(r'(?<=[.!?])\s+(?=[A-Z])|\n\s*\n',d['content'])]+[len(d['content'])]
            entries[-1]['citation_spans']=[{'start':a,'end':b} for a,b in zip(boundaries,boundaries[1:]) if b>a]
    question='how do these follow the conflicts between family or close people when fighting injustice'
    pack={'question':question,'entries':entries}
    if args.span_ids: pack['citation_span_kind']='sentence'
    expected='359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7'
    url='http://127.0.0.1:11435'; model='qwen3:4b'
    if shutil.disk_usage(area).free<6*1024**3: raise RuntimeError('disk_reserve')
    if local_model_digest(url,model)!=expected: raise ValueError('model_digest_mismatch')
    started=time.monotonic(); parts=[]; final=None
    prompt=messages(pack,span_ids=True,citation_first=True) if args.span_ids else [
        {'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(pack,ensure_ascii=False)}]
    schema=answer_schema(pack,span_ids=args.span_ids,citation_first=args.span_ids)
    if args.span_ids:
        # Ollama's grammar rejects JSON Schema prefixItems; enforce both-film
        # citation coverage afterwards via resolve_span_answer/validate_answer.
        schema['properties']['comparison']['properties']['support']={'type':'array','minItems':2,'maxItems':2,
            'items':{'type':'object','properties':{'ref':{'type':'string','enum':list(quote_spans(pack))}},
                     'required':['ref'],'additionalProperties':False}}
    with httpx.stream('POST',url+'/api/chat',timeout=300,json={'model':model,'stream':True,'think':False,
        'format':schema,'messages':prompt,
        'options':{'temperature':0,'seed':42,'num_ctx':8192,'num_predict':1536},'keep_alive':0}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if shutil.disk_usage(area).free<6*1024**3: raise RuntimeError('disk_reserve')
            if not line: continue
            item=json.loads(line)
            if item.get('error'): raise RuntimeError('generator_error')
            parts.append(item.get('message',{}).get('content',''))
            if sum(map(len,parts))>60000: raise ValueError('output_limit')
            if item.get('done'): final=item; break
    raw=''.join(parts); errors=[]
    if final is None or final.get('done_reason')!='stop': errors.append('generation_not_finished')
    resolved=None
    try: resolved=resolve_span_answer(raw,pack) if args.span_ids else validate_answer(raw,pack)
    except (ValueError,KeyError,TypeError) as exc: errors.append(str(exc))
    if local_model_digest(url,model)!=expected: errors.append('model_digest_changed')
    result={'question':question,'pack':pack,'corpus_fingerprint':corpus['fingerprint'],
        'model':model,'model_digest':expected,'seconds':time.monotonic()-started,'raw':raw,
        'citation_mode':'sentence_ids' if args.span_ids else 'copied_quotes','resolved_answer':resolved,
        'structural_errors':errors,'done_reason':final.get('done_reason') if final else None,
        'semantic_review':'pending','caution':'Curated source packet; not retrieval performance or validated answer.'}
    with output.open('x') as h: json.dump(result,h,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('seconds','structural_errors','done_reason','semantic_review')}))


if __name__=='__main__': main()
