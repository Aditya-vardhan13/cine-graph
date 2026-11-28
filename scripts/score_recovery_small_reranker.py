"""Compare fixed-pool parent rankings against source-bound development spans."""
import hashlib
import json
from pathlib import Path
import statistics

from app.services.corpus_build_manifest import canonical_digest


def main():
    area=Path('data/evaluation')
    corpus=json.loads((area/'recovery-ten-film-current-v1.json').read_text())
    capture=json.loads((area/'recovery-ten-qwen4b-depth20-reranker-pool-v1.json').read_text())
    small=json.loads((area/'recovery-minilm-depth20-development-v1.json').read_text())
    large=json.loads((area/'recovery-ten-qwen4b-reranker-development-v1.json').read_text())
    review=json.loads((area/'recovery-oracle-review-development-complete-v1.json').read_text())
    out=area/'recovery-minilm-depth20-development-score-v1.json'
    if out.exists(): raise FileExistsError(out)
    if (canonical_digest({k:v for k,v in corpus.items() if k!='fingerprint'})!=corpus['fingerprint']
            or capture['corpus_fingerprint']!=corpus['fingerprint']
            or review['source_corpus_fingerprint']!=corpus['fingerprint']
            or small['contract']['capture_fingerprint']!=canonical_digest(capture)
            or large['capture_fingerprint']!=hashlib.sha256(json.dumps(capture,sort_keys=True).encode()).hexdigest()
            or not small['complete'] or not large['complete']):
        raise ValueError('artifact_binding_failed')
    docs={d['chunk_id']:d for d in corpus['documents']}; labels={r['case_id']:r for r in review['cases']}
    if not (len(corpus['cases'])==len(capture['cases'])==len(small['cases'])==len(large['cases'])==30):
        raise ValueError('development_packet_incomplete')
    output=[]; timings=[]
    for source,frozen,s,l in zip(corpus['cases'],capture['cases'],small['cases'],large['cases'],strict=True):
        if any(r['case_id']!=source['case_id'] or r['question']!=source['question'] or r['film_qids']!=source['film_qids'] for r in (frozen,s,l)):
            raise ValueError('case_mismatch')
        label=labels[source['case_id']]; sides=[]
        timings.append(sum(s[f'{side}_elapsed_ms'] for side in ('first','second')))
        for side,qid in zip(('first','second'),source['film_qids'],strict=True):
            pool=frozen[f'{side}_pool']; pool_ids=[x['chunk_id'] for x in pool]
            if len(pool_ids)!=len(set(pool_ids)): raise ValueError('duplicate_pool')
            by_id={x['chunk_id']:x for x in pool}
            for item in pool:
                doc=docs[item['chunk_id']]
                if item['film_qid']!=qid or item['content']!=doc['content'] or item['source_snapshot_id']!=doc['source_snapshot_id']:
                    raise ValueError('source_mismatch')
            spans=[e for e in label['evidence'] if e['film_qid']==qid]
            for e in spans:
                doc=docs[e['passage_id']]
                if doc['content_sha256']!=e['content_sha256'] or doc['content'][e['start']:e['end']]!=e['quote']:
                    raise ValueError('review_span_mismatch')
            rankings={'small':s[f'{side}_ranking'],'large':l[f'{side}_ranking']}
            counts={}
            for name,ranking in rankings.items():
                ids=[x['chunk_id'] for x in ranking]
                if len(ids)!=len(set(ids)) or set(ids)!=set(pool_ids): raise ValueError('ranking_mismatch')
                if name=='small':
                    for item in ranking:
                        w=item['winning_window']; text=by_id[item['chunk_id']]['content']
                        if text[w['start']:w['end']]!=w['text']: raise ValueError('window_offset_mismatch')
                counts[name]=sum(any(item['chunk_id']==e['passage_id'] and e['quote'] in by_id[item['chunk_id']]['content'] for item in ranking[:5]) for e in spans)
            sides.append({'qid':qid,'spans':len(spans),'hits':counts})
        output.append({'case_id':source['case_id'],'answerability':label['answerability'],'sides':sides})
    complete=[x for x in output if x['answerability']=='complete']
    summary={name:{'spans':sum(s['hits'][name] for c in complete for s in c['sides']),
        'both_films_all_spans':sum(all(s['spans'] and s['hits'][name]==s['spans'] for s in c['sides']) for c in complete)} for name in ('small','large')}
    timings.sort(); report={'complete_cases':len(complete),'annotated_spans':sum(s['spans'] for c in complete for s in c['sides']),
        'summary':summary,'small_pair_ms_median':statistics.median(timings),'small_pair_ms_p95_nearest_rank':timings[28],
        'model_load_ms':small['model_load_ms'],'cases':output,'small_sha256':canonical_digest(small),
        'caution':'Single-reviewer development parent-passage inclusion; not answer accuracy or independent product validation.'}
    with out.open('x') as h: json.dump(report,h,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}))


if __name__=='__main__': main()
