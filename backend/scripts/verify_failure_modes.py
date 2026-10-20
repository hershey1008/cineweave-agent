"""Isolated process fault drill; does not stop or reconfigure running services."""
import asyncio
import json
import os
import uuid
from types import SimpleNamespace

from app.agent.orchestrator import process_message
from app.agent.schemas import MessageRequest, SessionState
from app.config import settings
from app.database import SessionLocal
from app.models import ChatSession, ChatTurn, User
from online.filtering import satisfies


async def main():
    # These overrides apply only to this disposable process.
    os.environ['SEMANTIC_URL'] = 'http://127.0.0.1:9'
    settings.redis_url = 'redis://127.0.0.1:9/0'
    import online.ranking
    online.ranking.get_ranking_service = lambda: SimpleNamespace(is_ready=False)
    reports = []
    for email in ['demo@cineweave.local', 'history@cineweave.local']:
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).one()
            sid = str(uuid.uuid4())
            db.add(ChatSession(session_id=sid, user_id=user.user_id,
                               title='故障注入验证', state_json=SessionState().model_dump(), state_version=0))
            db.commit()
            request = MessageRequest(message='120分钟以内的科幻片，不要恐怖片',
                client_message_id=str(uuid.uuid4()), expected_state_version=0, top_k=3)
            response = await process_message(db, user, sid, request)
            assert response['status'] == 'degraded', response['status']
            assert response['items'], 'Fallback should retain eligible catalog results'
            assert any(c.startswith('semantic:') for c in response['degraded_components'])
            if email.startswith('history'):
                assert any(c.startswith('deepfm:') for c in response['degraded_components'])
            state = SessionState.model_validate(response['active_constraints'])
            assert all(satisfies(item, state, set()) for item in response['items'])
            db.expire_all()
            assert db.query(ChatSession).filter_by(session_id=sid).one().state_version == 1
            assert db.query(ChatTurn).filter_by(session_id=sid).count() == 1
            assert await process_message(db, user, sid, request) == response
            reports.append({'persona': 'history' if email.startswith('history') else 'new',
                'status':response['status'], 'items':len(response['items']),
                'degraded_components':response['degraded_components'],
                'hard_filters_passed':True, 'postgres_persisted':True, 'idempotent_replay':True})
    print('CINEWEAVE_FAULT_REPORT=' + json.dumps({'cases':2,'passed':2,'results':reports}))


if __name__ == '__main__':
    asyncio.run(main())
