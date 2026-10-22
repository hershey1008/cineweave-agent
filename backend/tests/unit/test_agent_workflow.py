import asyncio

import pytest
from fastapi import HTTPException

from app.agent import workflow
from app.agent.llm_client import LLMServiceError
from app.agent.schemas import IntentPatch
from evaluation.orchestration_cases import CASES, FixtureTurn, normalized


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
async def test_graph_matches_frozen_legacy_business_response(case):
    with FixtureTurn(case) as fixture:
        legacy = await fixture.run("legacy")
        assert fixture.client.parse.await_count == 1
    with FixtureTurn(case) as fixture:
        graph = await fixture.run("langgraph")
        assert fixture.client.parse.await_count == 1
        fixture.db.add.assert_not_called()
        fixture.db.commit.assert_not_called()
        assert normalized(graph) == normalized(legacy)
        nodes = [n["node"] for n in graph["trace"]["orchestration"]["nodes"]]
        assert nodes[:2] == ["parse_intent", "apply_intent"]
        assert nodes[-1] == "assemble_response"
        if fixture.pipeline_calls:
            if graph["status"] != "clarify":
                assert "recheck_facts" in nodes
                fixture.db.expire_all.assert_called_once()
        else:
            assert "recheck_facts" not in nodes


@pytest.mark.parametrize("mode", ["legacy", "langgraph"])
@pytest.mark.parametrize("error,expected", [
    (LLMServiceError("timeout", status_code=504, kind="timeout"), 504),
    (LLMServiceError("auth", status_code=503, kind="authentication"), 503),
    (ValueError("invalid intent"), 422),
    (RuntimeError("provider unavailable"), 503),
])
async def test_intent_failure_preserves_error_and_does_not_retry_or_write(mode, error, expected):
    with FixtureTurn(CASES[0]) as fixture:
        fixture.client.parse.side_effect = error
        before = fixture.initial.model_dump()
        with pytest.raises(HTTPException) as caught:
            await fixture.run(mode)
        assert caught.value.status_code == expected
        assert fixture.client.parse.await_count == 1
        assert fixture.initial.model_dump() == before
        fixture.db.commit.assert_not_called()
        assert not fixture.pipeline_calls


@pytest.mark.parametrize("mode", ["legacy", "langgraph"])
@pytest.mark.parametrize("patch", [
    IntentPatch(set_fields={"user_id": 99}),
    IntentPatch(set_fields={"runtime_max": 0}),
    IntentPatch(action="replace", exclude_positions=[99]),
    IntentPatch(action="explain", exclude_positions=[99]),
])
async def test_invalid_business_patch_is_rejected(mode, patch):
    with FixtureTurn(CASES[0]) as fixture:
        fixture.client.parse.return_value = patch, {"calls": 1}
        with pytest.raises(HTTPException) as caught:
            await fixture.run(mode)
        assert caught.value.status_code == 422
        fixture.db.commit.assert_not_called()
        assert not fixture.pipeline_calls


async def test_parallel_turns_do_not_share_state_or_node_traces():
    async def one(runtime_max):
        # The branches do not use patched recommendation dependencies.
        fixture = FixtureTurn({"name": "clarify", "initial": {"runtime_max": runtime_max},
                               "patch": {"action": "clarify", "question": "请确认。"}})
        return await fixture.run("langgraph")
    results = await asyncio.gather(one(90), one(120))
    assert [r["active_constraints"]["runtime_max"] for r in results] == [90, 120]
    for result in results:
        assert len(result["trace"]["orchestration"]["nodes"]) == 4


async def test_cancellation_propagates_without_commit():
    fixture = FixtureTurn(CASES[0])
    waiting = asyncio.Event()
    async def slow_parse(*args):
        waiting.set()
        await asyncio.Event().wait()
    fixture.client.parse.side_effect = slow_parse
    task = asyncio.create_task(fixture.run("langgraph"))
    await asyncio.wait_for(waiting.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    fixture.db.commit.assert_not_called()


def test_default_mode_and_invalid_setting(monkeypatch):
    monkeypatch.delenv("AGENT_ORCHESTRATOR", raising=False)
    assert workflow.orchestration_mode() == "langgraph"
    monkeypatch.setenv("AGENT_ORCHESTRATOR", "legacy")
    assert workflow.orchestration_mode() == "legacy"
    monkeypatch.setenv("AGENT_ORCHESTRATOR", "typo")
    with pytest.raises(ValueError):
        workflow.orchestration_mode()
