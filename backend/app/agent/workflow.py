"""Single-turn LangGraph orchestration; business persistence stays in the API shell.

No checkpointer, autonomous tool loop, node retry, or additional model call is added.
AGENT_ORCHESTRATOR=legacy selects the frozen pre-refactor implementation explicitly.
"""

import logging
import os
import time
from functools import lru_cache
from typing_extensions import TypedDict

from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import ValidationError

from online.context import RecommendationContext
from online.context_pipeline import recommend_context
from online.filtering import satisfies
from .explanation_service import explain
from .llm_client import LLMServiceError
from .schemas import IntentPatch, SessionState
from .session_service import apply_patch
from .tools import movie_facts, resolve_titles, user_context
from .turn_runtime import TurnRuntime

logger = logging.getLogger(__name__)


class TurnState(TypedDict, total=False):
    initial: SessionState
    state: SessionState
    patch: IntentPatch
    llm_trace: dict
    items: list[dict]
    seen_ids: set[int]
    trace: dict
    pipeline_trace: dict
    reply: str
    status: str
    response: dict


def orchestration_mode():
    mode = os.getenv("AGENT_ORCHESTRATOR", "langgraph")
    if mode not in {"langgraph", "legacy"}:
        raise ValueError("AGENT_ORCHESTRATOR must be langgraph or legacy")
    return mode


def _raise_intent_error(exc, request_id):
    if isinstance(exc, LLMServiceError):
        logger.warning("cineweave_llm_failure request_id=%s kind=%s status=%s",
                       request_id, exc.kind, exc.status_code)
        raise HTTPException(exc.status_code, str(exc)) from None
    if isinstance(exc, ValidationError):
        message = exc.errors()[0].get("msg", "选片条件无效")
        raise HTTPException(422, message.removeprefix("Value error, ")) from None
    if isinstance(exc, (ValueError, TypeError)):
        raise HTTPException(422, str(exc)) from None
    raise HTTPException(503, "意图服务暂不可用，请稍后重试") from exc


async def parse_intent(state: TurnState, runtime: Runtime[TurnRuntime]):
    ctx = runtime.context
    try:
        patch, trace = await ctx.client.parse(ctx.request.message, state["initial"])
    except Exception as exc:
        _raise_intent_error(exc, ctx.request_id)
    return {"patch": patch, "llm_trace": trace}


async def apply_intent(state: TurnState, runtime: Runtime[TurnRuntime]):
    ctx = runtime.context
    try:
        updated = apply_patch(state["initial"], state["patch"])
    except Exception as exc:
        _raise_intent_error(exc, ctx.request_id)
    patch = state["patch"]
    return {"state": updated, "items": [], "reply": patch.question or "",
            "status": "clarify" if patch.action == "clarify" else "ok",
            "trace": {"parser_mode": ctx.client.mode, "llm": state["llm_trace"],
                      "degraded_components": [], "tools": [],
                      "intent_ms": round((time.perf_counter() - ctx.started) * 1000, 2)}}


async def clarify(state: TurnState, runtime: Runtime[TurnRuntime]):
    return {"state": state["initial"]}


async def reset(state: TurnState, runtime: Runtime[TurnRuntime]):
    return {"reply": "本次选片条件已清空。告诉我现在想看什么，我会重新选片。"}


async def explain_previous(state: TurnState, runtime: Runtime[TurnRuntime]):
    from app.models import ChatTurn

    ctx = runtime.context
    initial, patch = state["initial"], state["patch"]
    position = patch.exclude_positions[0] if patch.exclude_positions else 1
    if not 1 <= position <= len(initial.last_recommendation_ids):
        raise HTTPException(422, "请先获得一组推荐，再指定要解释的电影")
    selected_id = initial.last_recommendation_ids[position - 1]
    prior_turns = ctx.db.query(ChatTurn).filter(ChatTurn.session_id == ctx.session_id).order_by(
        ChatTurn.created_at.desc()).limit(100).all()
    selected = next((item for turn in prior_turns for item in turn.response_json.get("items", [])
                     if item["movie_id"] == selected_id), None)
    if selected is None:
        raise HTTPException(422, "该推荐已不在可恢复记录中，请重新选片")
    return {"items": [selected], "reply": selected["reason"]}


def _clarification(state, exc):
    return {"state": state["initial"], "status": "clarify", "reply": str(exc)}


async def recommend(state: TurnState, runtime: Runtime[TurnRuntime]):
    ctx = runtime.context
    updated = state["state"].model_copy(deep=True)
    trace = {**state["trace"], "tools": list(state["trace"]["tools"])}
    try:
        if state["patch"].reference_titles:
            updated.reference_movie_ids = resolve_titles(ctx.db, state["patch"].reference_titles)
            trace["tools"].append("resolve_movie")
        started = time.perf_counter()
        catalog = movie_facts(ctx.db)
        if updated.reference_movie_ids:
            reference = [catalog[mid] for mid in updated.reference_movie_ids if mid in catalog]
            ref_text = " ".join(m["title"] + ": " + m["description"][:500] for m in reference)
            query = (updated.semantic_query + "; similar to " + ref_text)[-1900:]
        else:
            query = updated.semantic_query
        features, seen = user_context(ctx.db, ctx.user)
        trace["context_db_ms"] = round((time.perf_counter() - started) * 1000, 2)
        effective = updated.model_copy(update={"semantic_query": query})
        context = RecommendationContext(effective, features, seen, ctx.request.top_k, ctx.request_id)
        trace["tools"] += ["get_user_context", "retrieve_candidates", "get_movie_facts"]
        items, pipeline_trace = await recommend_context(context, catalog)
        return {"state": updated, "items": items, "seen_ids": seen,
                "trace": trace, "pipeline_trace": pipeline_trace}
    except ValueError as exc:
        return {**_clarification(state, exc), "trace": trace}


async def recheck_facts(state: TurnState, runtime: Runtime[TurnRuntime]):
    ctx = runtime.context
    try:
        started = time.perf_counter()
        ctx.db.expire_all()
        fresh_catalog = movie_facts(ctx.db, [item["movie_id"] for item in state["items"]])
        checked = []
        for item in state["items"]:
            fresh = fresh_catalog.get(item["movie_id"])
            if fresh is None or not satisfies(fresh, state["state"], state["seen_ids"]):
                continue
            reason, evidence = explain(fresh, item, state["state"])
            checked.append({**item, **fresh, "reason": reason, "evidence": evidence,
                            "final_rank": len(checked) + 1})
        pipeline_trace = {**state["pipeline_trace"],
                          "final_recheck_removed": len(state["items"]) - len(checked),
                          "final_recheck_ms": round((time.perf_counter() - started) * 1000, 2)}
        trace = {**state["trace"], **pipeline_trace, "parser_mode": ctx.client.mode}
        updated = state["state"].model_copy(deep=True)
        updated.last_recommendation_ids = [c["movie_id"] for c in checked]
        status = state["status"]
        if checked:
            reply = f"为你选出 {len(checked)} 部电影，已核对当前筛选条件。"
            if len(checked) < ctx.request.top_k:
                reply += " 符合条件的候选不足，未自动放宽限制。"
            if trace["degraded_components"]:
                status = "degraded"
                reply += " 部分推荐组件暂不可用，已使用可用通道。"
        else:
            status = "no_results"
            reply = "当前目录没有符合全部条件的电影。可以放宽年份、时长或类型条件；我会等你确认后再修改。"
        return {"state": updated, "items": checked, "trace": trace, "reply": reply, "status": status}
    except ValueError as exc:
        return _clarification(state, exc)


async def assemble_response(state: TurnState, runtime: Runtime[TurnRuntime]):
    ctx = runtime.context
    trace = {**state["trace"], "total_ms": round((time.perf_counter() - ctx.started) * 1000, 2)}
    return {"response": {"status": state["status"], "reply": state["reply"], "items": state["items"],
                         "active_constraints": state["state"].model_dump(), "request_id": ctx.request_id,
                         "state_version": ctx.version + 1, "parser_mode": ctx.client.mode,
                         "degraded_components": trace.get("degraded_components", []), "trace": trace,
                         "clarification": state["reply"] if state["status"] == "clarify" else None}}


def _observed(name, node):
    async def observed(state: TurnState, runtime: Runtime[TurnRuntime]):
        started = time.perf_counter()
        try:
            return await node(state, runtime)
        finally:
            runtime.context.node_events.append({"node": name,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)})
    return observed


@lru_cache(maxsize=1)
def get_turn_graph():
    builder = StateGraph(TurnState, context_schema=TurnRuntime)
    nodes = {"parse_intent": parse_intent, "apply_intent": apply_intent, "clarify": clarify,
             "reset": reset, "explain_previous": explain_previous, "recommend": recommend,
             "recheck_facts": recheck_facts, "assemble_response": assemble_response}
    for name, node in nodes.items():
        builder.add_node(name, _observed(name, node))
    builder.add_edge(START, "parse_intent")
    builder.add_edge("parse_intent", "apply_intent")
    builder.add_conditional_edges("apply_intent", lambda s: s["patch"].action, {
        "clarify": "clarify", "reset": "reset", "explain": "explain_previous",
        "recommend": "recommend", "replace": "recommend"})
    builder.add_conditional_edges("recommend", lambda s: s["status"] == "clarify", {
        True: "assemble_response", False: "recheck_facts"})
    for name in ["clarify", "reset", "explain_previous", "recheck_facts"]:
        builder.add_edge(name, "assemble_response")
    builder.add_edge("assemble_response", END)
    return builder.compile()


async def run_turn(initial, runtime, *, mode=None):
    mode = orchestration_mode() if mode is None else mode
    if mode == "legacy":
        from .legacy_turn import run_legacy_turn
        started = time.perf_counter()
        response = await run_legacy_turn(initial, runtime)
        runtime.node_events.append({"node": "legacy_turn",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)})
    elif mode == "langgraph":
        result = await get_turn_graph().ainvoke({"initial": initial}, context=runtime)
        response = result["response"]
    else:
        raise ValueError("Unknown orchestration mode")
    response["trace"]["orchestration"] = {"backend": mode, "nodes": list(runtime.node_events)}
    response["trace"]["total_ms"] = round((time.perf_counter() - runtime.started) * 1000, 2)
    return response
