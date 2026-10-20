import asyncio
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.models import ChatSession, ChatTurn, RecommendationEvent, RecommendationFeedback, User
from app.agent.schemas import EventRequest, FeedbackRequest, MessageRequest, SessionState
from app.agent.orchestrator import own_session, process_message

router = APIRouter()


@router.post("/chat/sessions", status_code=201)
def create_session(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = ChatSession(session_id=str(uuid.uuid4()), user_id=user.user_id,
                          state_json=SessionState().model_dump(), state_version=0)
    db.add(session)
    db.commit()
    return {"session_id": session.session_id, "state_version": 0, "active_constraints": session.state_json}


@router.get("/chat/sessions")
def list_sessions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sessions = db.query(ChatSession).filter(ChatSession.user_id == user.user_id).order_by(ChatSession.updated_at.desc()).limit(30).all()
    return {"items": [{"session_id": s.session_id, "title": s.title,
                       "state_version": s.state_version, "updated_at": s.updated_at.isoformat()} for s in sessions]}


@router.get("/chat/sessions/{session_id}")
def get_session(session_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = own_session(db, session_id, user.user_id)
    query = db.query(ChatTurn).filter(ChatTurn.session_id == session_id)
    turns = query.order_by(ChatTurn.created_at.desc()).offset(offset).limit(limit).all()
    return {"session_id": session_id, "title": session.title,
            "state_version": session.state_version, "active_constraints": session.state_json,
            "turns": [{"message": t.user_text, "response": t.response_json} for t in reversed(turns)],
            "total_turns": query.count()}


@router.post("/chat/sessions/{session_id}/messages")
async def send_message(session_id: str, request: MessageRequest,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return await asyncio.wait_for(process_message(db, user, session_id, request),
                                       timeout=float(os.getenv("CHAT_TIMEOUT", "20")))
    except asyncio.TimeoutError:
        db.rollback()
        raise HTTPException(504, "本轮处理超时，状态未提交。请使用相同消息 ID 重试。") from None


def validate_recommendation(db, session_id, request_id, movie_id, user_id):
    own_session(db, session_id, user_id)
    turn = db.query(ChatTurn).filter(ChatTurn.session_id == session_id, ChatTurn.request_id == request_id).first()
    if turn is None or movie_id not in [i["movie_id"] for i in turn.response_json.get("items", [])]:
        raise HTTPException(422, "电影不属于该次推荐")


@router.post("/chat/sessions/{session_id}/feedback")
def feedback(session_id: str, request: FeedbackRequest,
             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    validate_recommendation(db, session_id, request.request_id, request.movie_id, user.user_id)
    existing = db.get(RecommendationFeedback, request.event_id)
    if existing:
        if (existing.user_id, existing.session_id, existing.movie_id, existing.request_id, existing.feedback_type) != (
            user.user_id, session_id, request.movie_id, request.request_id, request.feedback_type):
            raise HTTPException(409, "反馈 ID 已用于其他内容")
        return {"ok": True, "duplicate": True, "state_version": own_session(db, session_id, user.user_id).state_version}
    session = own_session(db, session_id, user.user_id)
    version = session.state_version
    if request.feedback_type in {"seen", "dislike"}:
        state = SessionState.model_validate(session.state_json)
        state.excluded_movie_ids = list(dict.fromkeys(state.excluded_movie_ids + [request.movie_id]))
        result = db.execute(update(ChatSession).where(ChatSession.session_id == session_id,
            ChatSession.state_version == version).values(state_json=state.model_dump(), state_version=version + 1,
                                                       updated_at=datetime.now(timezone.utc)))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "会话已更新，请重试反馈")
        version += 1
    db.add(RecommendationFeedback(feedback_id=request.event_id, user_id=user.user_id,
        session_id=session_id, request_id=request.request_id, movie_id=request.movie_id,
        feedback_type=request.feedback_type))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "反馈正在提交，请使用相同事件 ID 重试") from None
    return {"ok": True, "duplicate": False, "state_version": version}


@router.post("/recommendation-events")
def event(request: EventRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    validate_recommendation(db, request.session_id, request.request_id, request.movie_id, user.user_id)
    existing = db.get(RecommendationEvent, request.event_id)
    if existing:
        if (existing.user_id, existing.session_id, existing.request_id, existing.movie_id, existing.event_type) != (
            user.user_id, request.session_id, request.request_id, request.movie_id, request.event_type):
            raise HTTPException(409, "事件 ID 已用于其他内容")
        return {"ok": True, "duplicate": True}
    db.add(RecommendationEvent(event_id=request.event_id, user_id=user.user_id, session_id=request.session_id,
        request_id=request.request_id, movie_id=request.movie_id, event_type=request.event_type))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "事件正在提交，请使用相同事件 ID 重试") from None
    return {"ok": True, "duplicate": False}
