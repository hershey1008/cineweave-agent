"""Small live LLM regression; uses synthetic demo requests, never prints credentials."""
import json
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
MESSAGES = ['想看关于太空探索的科幻片，120分钟以内，不要恐怖片',
            '轻松一点，其他要求不变', '第三部看过了，换一部', '时长不限了', '为什么推荐第一部？']


def run():
    report = {'protocol':'live_llm_five_turn_regression_v1','turns':[], 'passed':False}
    try:
        with httpx.Client(base_url='http://127.0.0.1:13000', timeout=70, trust_env=False) as client:
            for _ in range(15):
                try:
                    health = client.get('/api/agent/health',timeout=3)
                    if health.is_success and health.json().get('ready'):
                        break
                except (httpx.HTTPError,ValueError):
                    pass
                time.sleep(2)
            else:
                raise RuntimeError('Backend not ready')
            assert health.json()['parser_mode']=='llm', 'LLM not configured'
            auth = client.post('/api/auth/login',json={'email':'demo@cineweave.local','password':'CineweaveDemo!2026'})
            auth.raise_for_status()
            client.headers['Authorization']='Bearer '+auth.json()['access_token']
            session=client.post('/api/chat/sessions')
            session.raise_for_status()
            sid=session.json()['session_id']
            version=0
            previous=[]
            replaced=None
            for i,message in enumerate(MESSAGES):
                started=time.perf_counter()
                response=client.post(f'/api/chat/sessions/{sid}/messages',json={'message':message,
                    'client_message_id':str(uuid.uuid4()),'expected_state_version':version,'top_k':3})
                row={'turn':i+1,'http_status':response.status_code,'elapsed_seconds':round(time.perf_counter()-started,2)}
                report['turns'].append(row)
                if not response.is_success:
                    row['passed']=False
                    raise RuntimeError('Message HTTP '+str(response.status_code))
                data=response.json()
                state=data['active_constraints']
                llm=data.get('trace',{}).get('llm',{})
                items=data.get('items',[])
                checks={'llm_used':data['parser_mode']=='llm' and llm.get('calls',0)>=1,
                    'ok':data['status']=='ok', 'has_results':bool(items),
                    'genres_retained':state['include_genres']==['Sci-Fi'] and state['exclude_genres']==['Horror'],
                    'runtime_state':state['runtime_max']==(120 if i<3 else None),
                    'hard_filters':all('Sci-Fi' in m['genres'] and 'Horror' not in m['genres']
                        and (state['runtime_max'] is None or (m.get('runtime_minutes') and m['runtime_minutes']<=120)) for m in items)}
                if i==2:
                    replaced=previous[2]
                if i>=2:
                    checks['replacement_retained']=replaced in state['excluded_movie_ids'] and replaced not in [m['movie_id'] for m in items]
                if i==4:
                    checks['explains_previous_first']=len(items)==1 and items[0]['movie_id']==previous[0]
                row.update(status=data['status'],parser_mode=data['parser_mode'],llm_calls=llm.get('calls'),llm_tokens=llm.get('tokens'),
                    llm_elapsed_ms=llm.get('elapsed_ms'),checks=checks,passed=all(checks.values()),
                    items=[{'title':m['title'],'runtime_minutes':m['runtime_minutes']} for m in items])
                print(json.dumps(row,ensure_ascii=True),flush=True)
                if not row['passed']:
                    raise RuntimeError('Conversation expectation failed')
                previous=[m['movie_id'] for m in items]
                version=data['state_version']
            report['passed']=True
    except Exception as exc:
        # Report exception class only; upstream error text can contain endpoint details.
        report['error_type']=type(exc).__name__
    output=ROOT/'evaluation/reports/generated/llm-live-regression.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'turns':len(report['turns']),'error_type':report.get('error_type')}),flush=True)
    return report


if __name__=='__main__':
    raise SystemExit(not run()['passed'])
