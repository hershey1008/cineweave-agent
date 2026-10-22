import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.models import ChatSession, ChatTurn
from .llm_client import LLMClient
from .schemas import SessionState
from .turn_runtime import TurnRuntime
from .workflow import run_turn

logger = logging.getLogger(__name__)


def own_session(db, session_id, user_id):
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id, ChatSession.user_id == user_id).first()
    if session is None:
        raise HTTPException(404, "会话不存在")
    return session


def replay(db, session_id, request):
    previous = db.query(ChatTurn).filter(ChatTurn.session_id == session_id,
        ChatTurn.client_message_id == request.client_message_id).first()
    if previous:
        if previous.user_text != request.message or previous.top_k != request.top_k:
            raise HTTPException(409, "同一消息 ID 不能提交不同内容")
        return previous.response_json
    return None


async def process_message(db, user, session_id, request):
    started = time.perf_counter()
    session = own_session(db, session_id, user.user_id)
    previous = replay(db, session_id, request)
    if previous:
        return previous
    if session.state_version != request.expected_state_version:
        raise HTTPException(409, "会话已更新，请恢复最新状态后重试")
    initial = SessionState.model_validate(session.state_json)
    version = session.state_version
    old_title = session.title
    db.commit()  # Release the read transaction before model / network work.
    request_id = str(uuid.uuid4())
    runtime = TurnRuntime(db=db, user=user, request=request, session_id=session_id, request_id=request_id,
                          started=started, version=version, client=LLMClient())
    response = await run_turn(initial, runtime)
    state = SessionState.model_validate(response["active_constraints"])
    trace = response["trace"]
    client = runtime.client
    try:
        updated = db.execute(update(ChatSession).where(ChatSession.session_id == session_id,
            ChatSession.user_id == user.user_id, ChatSession.state_version == version)
            .values(state_json=state.model_dump(), state_version=version + 1,
                    title=request.message[:60] if version == 0 else old_title,
                    updated_at=datetime.now(timezone.utc)))
        if updated.rowcount != 1:
            db.rollback()
            previous = replay(db, session_id, request)
            if previous:
                return previous
            raise HTTPException(409, "会话已被另一条消息更新，请恢复后重试")
        db.add(ChatTurn(turn_id=str(uuid.uuid4()), session_id=session_id,
            client_message_id=request.client_message_id, request_id=request_id,
            user_text=request.message, top_k=request.top_k, response_json=response))
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = replay(db, session_id, request)
        if previous:
            return previous
        raise HTTPException(409, "消息写入冲突，请重试")
    try:
        import redis
        from app.config import settings
        cache = redis.Redis.from_url(settings.redis_url, socket_timeout=0.3, socket_connect_timeout=0.3)
        cache.setex(f"cw:session:{user.user_id}:{session_id}", 86400, json.dumps(response, ensure_ascii=False))
    except Exception:
        logger.info("Session cache unavailable; PostgreSQL remains authoritative")
    logger.info("cineweave_turn %s", json.dumps({"request_id": request_id, "status": response["status"],
        "parser_mode": client.mode, "total_ms": trace["total_ms"]}))
    return response
