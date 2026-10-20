"""Collect real ES/semantic runs for later independent relevance annotation."""
import argparse
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def run(limit):
    index_root = ROOT / 'artifacts/semantic_index'
    active = json.loads((index_root/'active.json').read_text(encoding='utf-8'))
    documents = [json.loads(line) for line in (index_root/active['version']/'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    allowed = {d['movie_id'] for d in documents}
    queries = [json.loads(line) for line in (ROOT/'evaluation/datasets/retrieval_queries.jsonl').read_text(encoding='utf-8').splitlines()]
    if limit:
        queries = queries[:limit]
    results = {'elasticsearch': [], 'semantic': []}
    with httpx.Client(timeout=25,trust_env=False) as client:
        for query in queries:
            lexical = client.get('http://127.0.0.1:18000/api/search/movies',params={'q':query['query'],'limit':20})
            lexical.raise_for_status()
            semantic = client.post('http://127.0.0.1:18010/search',json={'text':query['query'],
                'eligible_ids':sorted(allowed),'top_k':20,'expected_version':active['version']})
            semantic.raise_for_status()
            results['elasticsearch'].append({'query_id':query['query_id'],
                'movie_ids':[m['movie_id'] for m in lexical.json() if m['movie_id'] in allowed]})
            results['semantic'].append({'query_id':query['query_id'],
                'movie_ids':[m['movie_id'] for m in semantic.json()['items']]})
            print(query['query_id'],flush=True)
    output=ROOT/'evaluation/reports/generated'
    output.mkdir(parents=True,exist_ok=True)
    for name, rows in results.items():
        (output/f'{name}-retrieval.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
    print('Runs saved; no quality metrics computed because human relevance labels are pending.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=0)
    args=parser.parse_args()
    run(args.limit)
