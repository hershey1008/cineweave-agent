"""Frozen pre-LangGraph turn logic for explicit parity comparisons and rollback.

Session authorization, idempotency and commits remain in orchestrator.py.
"""

import logging
import time

from fastapi import HTTPException
from pydantic import ValidationError

from app.models import ChatTurn
from online.context import RecommendationContext
from online.context_pipeline import recommend_context
from online.filtering import satisfies
from .explanation_service import explain
from .llm_client import LLMServiceError
from .session_service import apply_patch
from .tools import movie_facts, resolve_titles, user_context

logger = logging.getLogger(__name__)


async def run_legacy_turn(initial, runtime):
    db, user, request = runtime.db, runtime.user, runtime.request
    session_id = runtime.session_id
    started, version = runtime.started, runtime.version
    client = runtime.client
    request_id = runtime.request_id
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
    return response
