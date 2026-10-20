import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from app.models import ChatSession, ChatTurn
from online.context import RecommendationContext
from online.context_pipeline import recommend_context
from online.filtering import satisfies
from .explanation_service import explain
from .llm_client import LLMClient, LLMServiceError
from .schemas import SessionState
from .session_service import apply_patch
from .tools import movie_facts, resolve_titles, user_context

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
    client = LLMClient()
    request_id = str(uuid.uuid4())
    try:
        patch, llm_trace = await client.parse(request.message, initial)
        state = apply_patch(initial, patch)
    except LLMServiceError as exc:
        logger.warning("cineweave_llm_failure request_id=%s kind=%s status=%s", request_id, exc.kind, exc.status_code)
        raise HTTPException(exc.status_code, str(exc)) from None
    except ValidationError as exc:
        message = exc.errors()[0].get("msg", "选片条件无效")
        raise HTTPException(422, message.removeprefix("Value error, ")) from None
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception as exc:
        raise HTTPException(503, "意图服务暂不可用，请稍后重试") from exc
    items = []
    trace = {"parser_mode": client.mode, "llm": llm_trace, "degraded_components": [], "tools": [],
             "intent_ms": round((time.perf_counter() - started) * 1000, 2)}
    reply = patch.question or ""
    status = "clarify" if patch.action == "clarify" else "ok"
    if patch.action == "clarify":
        state = initial
    elif patch.action == "reset":
        reply = "本次选片条件已清空。告诉我现在想看什么，我会重新选片。"
    elif patch.action == "explain":
        position = patch.exclude_positions[0] if patch.exclude_positions else 1
        if not 1 <= position <= len(initial.last_recommendation_ids):
            raise HTTPException(422, "请先获得一组推荐，再指定要解释的电影")
        selected_id = initial.last_recommendation_ids[position - 1]
        prior_turns = db.query(ChatTurn).filter(ChatTurn.session_id == session_id).order_by(ChatTurn.created_at.desc()).limit(100).all()
        selected = next((item for turn in prior_turns for item in turn.response_json.get("items", [])
                         if item["movie_id"] == selected_id), None)
        if selected is None:
            raise HTTPException(422, "该推荐已不在可恢复记录中，请重新选片")
        items = [selected]
        reply = items[0]["reason"]
    else:
        try:
            if patch.reference_titles:
                state.reference_movie_ids = resolve_titles(db, patch.reference_titles)
                trace["tools"].append("resolve_movie")
            facts_started = time.perf_counter()
            catalog = movie_facts(db)
            if state.reference_movie_ids:
                reference = [catalog[mid] for mid in state.reference_movie_ids if mid in catalog]
                ref_text = " ".join(m["title"] + ": " + m["description"][:500] for m in reference)
                query = (state.semantic_query + "; similar to " + ref_text)[-1900:]
            else:
                query = state.semantic_query
            features, seen = user_context(db, user)
            trace["context_db_ms"] = round((time.perf_counter() - facts_started) * 1000, 2)
            effective = state.model_copy(update={"semantic_query": query})
            context = RecommendationContext(effective, features, seen, request.top_k, request_id)
            trace["tools"] += ["get_user_context", "retrieve_candidates", "get_movie_facts"]
            items, pipeline_trace = await recommend_context(context, catalog)
            # Re-read business facts after network/model work, before presenting results.
            recheck_started = time.perf_counter()
            db.expire_all()
            fresh_catalog = movie_facts(db, [item["movie_id"] for item in items])
            checked = []
            for item in items:
                fresh = fresh_catalog.get(item["movie_id"])
                if fresh is None or not satisfies(fresh, state, seen):
                    continue
                reason, evidence = explain(fresh, item, state)
                checked.append({**item, **fresh, "reason": reason, "evidence": evidence,
                                "final_rank": len(checked) + 1})
            pipeline_trace["final_recheck_removed"] = len(items) - len(checked)
            pipeline_trace["final_recheck_ms"] = round((time.perf_counter() - recheck_started) * 1000, 2)
            items = checked
            trace.update(pipeline_trace)
            trace["parser_mode"] = client.mode
            if items:
                state.last_recommendation_ids = [c["movie_id"] for c in items]
                reply = f"为你选出 {len(items)} 部电影，已核对当前筛选条件。"
                if len(items) < request.top_k:
                    reply += " 符合条件的候选不足，未自动放宽限制。"
                if trace["degraded_components"]:
                    status = "degraded"
                    reply += " 部分推荐组件暂不可用，已使用可用通道。"
            else:
                state.last_recommendation_ids = []
                status = "no_results"
                reply = "当前目录没有符合全部条件的电影。可以放宽年份、时长或类型条件；我会等你确认后再修改。"
        except ValueError as exc:
            state = initial
            status = "clarify"
            reply = str(exc)
    trace["total_ms"] = round((time.perf_counter() - started) * 1000, 2)
    response = {"status": status, "reply": reply, "items": items,
        "active_constraints": state.model_dump(), "request_id": request_id,
        "state_version": version + 1, "parser_mode": client.mode,
        "degraded_components": trace.get("degraded_components", []), "trace": trace,
        "clarification": reply if status == "clarify" else None}
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
    logger.info("cineweave_turn %s", json.dumps({"request_id": request_id, "status": status,
        "parser_mode": client.mode, "total_ms": trace["total_ms"]}))
    return response
