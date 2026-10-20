"""Exercise a standard backend image against existing local demo infrastructure."""
import json
import logging
import uuid

logging.basicConfig(level=logging.WARNING)
from fastapi.testclient import TestClient
from app.main import app


def main():
    checks=[]
    with TestClient(app) as client:
        health=client.get('/api/agent/health')
        assert health.status_code==200 and health.json()['ready']
        checks.append('health_ready')
        for email in ['demo@cineweave.local','history@cineweave.local']:
            auth=client.post('/api/auth/login',json={'email':email,'password':'CineweaveDemo!2026'})
            assert auth.status_code==200
            headers={'Authorization':'Bearer '+auth.json()['access_token']}
            created=client.post('/api/chat/sessions',headers=headers)
            assert created.status_code==201
            sid=created.json()['session_id']
            response=client.post(f'/api/chat/sessions/{sid}/messages',headers=headers,json={
                'message':'120分钟以内的科幻片，不要恐怖片','client_message_id':str(uuid.uuid4()),
                'expected_state_version':0,'top_k':3})
            assert response.status_code==200,response.status_code
            data=response.json()
            assert data['status']=='ok' and data['items'] and not data['degraded_components']
            assert all('Sci-Fi' in m['genres'] and 'Horror' not in m['genres'] and m['runtime_minutes']<=120 for m in data['items'])
            if email.startswith('history'):
                assert all(data['trace']['channels'].get(c,0)>0 for c in ['semantic','youtubednn','item_based','genre_preference'])
                assert data['trace']['deepfm_ms']>0
            checks.append('history_real_models' if email.startswith('history') else 'new_user_semantic')
    print('PORTABLE_RUNTIME_REPORT='+json.dumps({'passed':True,'checks':checks}))


if __name__=='__main__':
    main()
