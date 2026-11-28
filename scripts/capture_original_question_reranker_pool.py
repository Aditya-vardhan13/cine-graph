"""Prepare the retained original user-question pool without source mutation."""
import json
from pathlib import Path
from app.services.corpus_build_manifest import canonical_digest


def main():
    area=Path('data/evaluation')
    source=json.loads((area/'recovery-inactive-live-db-probes-v1.json').read_text())
    corpus=json.loads((area/'recovery-ten-film-current-v1.json').read_text())
    out=area/'recovery-original-question-small-pool-v1.json'
    if out.exists(): raise FileExistsError(out)
    p=source['probes'][0]
    if [s['qid'] for s in p['sides']]!=['Q23781155','Q47703']:
        raise ValueError('unexpected_user_question_scope')
    titles={d['film_qid']:d['film_title'] for d in corpus['documents']}
    case={'case_id':'original-endgame-godfather','question':p['question'],
          'film_qids':[s['qid'] for s in p['sides']],
          'titles':[titles[s['qid']] for s in p['sides']]}
    for name,side in zip(('first','second'),p['sides'],strict=True):
        rows=side['methods']['semantic']['evidence']
        if len(rows)!=10 or any(r['source_snapshot_id'] not in
                {d['source_snapshot_id'] for d in corpus['documents'] if d['film_qid']==side['qid']} for r in rows):
            raise ValueError('source_pool_mismatch')
        case[name+'_pool']=rows
    result={'method':'candidate-union','corpus_fingerprint':corpus['fingerprint'],
            'input_sha256':canonical_digest(source),'cases':[case]}
    with out.open('x') as h: json.dump(result,h,ensure_ascii=False,indent=2)
    print(str(out))


if __name__=='__main__': main()
