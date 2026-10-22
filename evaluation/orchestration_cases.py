"""Deterministic orchestration fixtures, not live retrieval or LLM quality tests."""

import time
from copy import deepcopy
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.agent import legacy_turn, workflow
from app.agent.schemas import IntentPatch, MessageRequest, SessionState
from app.agent.turn_runtime import TurnRuntime


MOVIE = {"movie_id": 42, "title": "Fixture Movie", "year": 1999,
         "genres": ["Sci-Fi"], "runtime_minutes": 100, "description": "Space exploration.",
         "title_type": "movie", "isAdult": 0, "rating_count": 80, "imdb_rating": 8.0}

CASES = [
    {"name": "recommend", "patch": {"set_fields": {"runtime_max": 120}}},
    {"name": "replace_third", "initial": {"last_recommendation_ids": [10, 20, 30]},
     "patch": {"action": "replace", "exclude_positions": [3]}},
    {"name": "preserve_constraints", "initial": {"runtime_max": 120, "exclude_genres": ["Horror"]},
     "patch": {"set_fields": {"semantic_query": "lighthearted"}}},
    {"name": "clear_runtime", "initial": {"runtime_max": 120, "include_genres": ["Sci-Fi"]},
     "patch": {"clear_fields": ["runtime_max"]}},
    {"name": "clarify", "initial": {"runtime_max": 120},
     "patch": {"action": "clarify", "question": "最多多少分钟？"}},
    {"name": "reset", "initial": {"runtime_max": 120}, "patch": {"action": "reset"}},
    {"name": "explain", "initial": {"last_recommendation_ids": [42]},
     "patch": {"action": "explain", "exclude_positions": [1]}},
    {"name": "reference_movie", "patch": {"reference_titles": ["Fixture Movie"]}},
    {"name": "missing_reference", "patch": {"reference_titles": ["Missing"]}, "missing_reference": True},
    {"name": "no_results", "patch": {}, "empty": True},
    {"name": "component_degraded", "patch": {}, "degraded": ["semantic:TimeoutError"]},
    {"name": "changed_facts", "patch": {"set_fields": {"runtime_max": 120}}, "changed_facts": True},
    {"name": "deleted_movie", "patch": {}, "deleted_movie": True},
]


def normalized(value):
    """Exclude timing/implementation metadata only; compare all business fields."""
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()
                if not k.endswith("_ms") and k != "orchestration"}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


class FixtureTurn:
    def __init__(self, case):
        self.case = case
        self.initial = SessionState(**case.get("initial", {}))
        self.client = SimpleNamespace(mode="fixture", parse=AsyncMock(return_value=(
            IntentPatch(**case["patch"]), {"mode": "fixture", "calls": 1, "tokens": 0})))
        self.db = Mock()
        prior = {**MOVIE, "reason": "既有事实解释。", "evidence": [], "final_rank": 1}
        self.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            SimpleNamespace(response_json={"items": [prior]})]
        self.request = MessageRequest(message=case["name"], client_message_id="fixture-message",
                                      expected_state_version=2, top_k=2)
        self.runtime = TurnRuntime(db=self.db, user=SimpleNamespace(user_id=7), request=self.request,
            session_id="fixture-session", request_id="fixture-request", started=time.perf_counter(),
            version=2, client=self.client)
        self.pipeline_calls = []
        self.stack = ExitStack()

    def facts(self, db, ids=None):
        if ids is not None and (not ids or self.case.get("deleted_movie")):
            return {}
        movie = deepcopy(MOVIE)
        if ids is not None and self.case.get("changed_facts"):
            movie["runtime_minutes"] = 150
        return {42: movie}

    async def pipeline(self, context, catalog):
        self.pipeline_calls.append(context)
        return ([] if self.case.get("empty") else [{**MOVIE, "recall_sources": ["semantic"], "final_rank": 1}],
                {"degraded_components": self.case.get("degraded", []), "candidate_count": 1,
                 "channels": {"fixture": 1}, "ranking_ms": 0})

    def __enter__(self):
        for module in [workflow, legacy_turn]:
            self.stack.enter_context(patch.object(module, "movie_facts", self.facts))
            self.stack.enter_context(patch.object(module, "user_context", return_value=({"user_id": 7}, set())))
            self.stack.enter_context(patch.object(module, "recommend_context", self.pipeline))
            resolver = self.stack.enter_context(patch.object(module, "resolve_titles", return_value=[42]))
            if self.case.get("missing_reference"):
                resolver.side_effect = ValueError("参考片不存在，请补充片名。")
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)

    async def run(self, mode):
        self.runtime.started = time.perf_counter()
        return await workflow.run_turn(self.initial.model_copy(deep=True), self.runtime, mode=mode)
