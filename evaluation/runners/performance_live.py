"""Warm local rule-mode service load test; no LLM latency claims."""
import argparse
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
QUERIES = ["120分钟以内的科幻片", "100分钟以内的喜剧", "90年代的剧情片", "关于太空探索的科幻片",
           "温暖的爱情电影", "关于成长和友谊的剧情片", "90年代的动作片", "魔法与奇幻冒险",
           "轻松的喜剧电影", "关于机器人与人类的科幻片"]


def run(count, concurrency):
    with httpx.Client(base_url="http://127.0.0.1:18000", timeout=25, trust_env=False) as client:
        auth = client.post('/api/auth/login', json={'email':'demo@cineweave.local','password':'CineweaveDemo!2026'})
        auth.raise_for_status()
        headers = {'Authorization':'Bearer '+auth.json()['access_token']}
    def request(i):
        with httpx.Client(base_url="http://127.0.0.1:18000", headers=headers, timeout=25, trust_env=False) as client:
            session = client.post('/api/chat/sessions')
            session.raise_for_status()
            sid = session.json()['session_id']
            started = time.perf_counter()
            try:
                result = client.post(f'/api/chat/sessions/{sid}/messages', json={
                    'message':QUERIES[i%len(QUERIES)],'client_message_id':str(uuid.uuid4()),
                    'expected_state_version':0,'top_k':3})
                data = result.json()
                return {'status_code':result.status_code, 'elapsed_ms':(time.perf_counter()-started)*1000,
                    'parser_mode':data.get('parser_mode'), 'degraded':data.get('degraded_components'),
                    'semantic_cache_hit':data.get('trace',{}).get('semantic',{}).get('cache_hit')}
            except Exception as exc:
                return {'status_code':0,'elapsed_ms':(time.perf_counter()-started)*1000,'error':type(exc).__name__}
    warmup = [request(i) for i in range(len(QUERIES))]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(request, range(count)))
    elapsed = time.perf_counter()-started
    latency = [r['elapsed_ms'] for r in results]
    report = {'protocol':'warm_local_rules_v1','count':count,'concurrency':concurrency,
        'successful_http':sum(r['status_code']==200 for r in results),
        'degraded_responses':sum(bool(r.get('degraded')) for r in results),
        'p50_ms':float(np.percentile(latency,50)), 'p95_ms':float(np.percentile(latency,95)),
        'wall_seconds':elapsed,'requests_per_second':count/elapsed,
        'llm_not_configured':True,'cache_policy':'10 mixed query texts warmed before measurement',
        'warmup':warmup,'results':results}
    output=ROOT/f'evaluation/reports/generated/performance-c{concurrency}.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'results','warmup'}}))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--count',type=int,default=200)
    parser.add_argument('--concurrency',type=int,default=5)
    args=parser.parse_args()
    report=run(args.count,args.concurrency)
    raise SystemExit(report['successful_http']!=args.count or report['degraded_responses']!=0)
