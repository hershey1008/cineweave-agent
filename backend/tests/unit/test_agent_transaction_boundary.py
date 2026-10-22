from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.agent import orchestrator
from app.agent.schemas import MessageRequest, SessionState
from app.models import ChatSession, ChatTurn


@pytest.fixture
def boundary(monkeypatch):
    session = SimpleNamespace(session_id="session", user_id=7, state_version=2,
                              state_json=SessionState(runtime_max=120).model_dump(), title="Existing")
    db = Mock()
    session_query, turn_query = Mock(), Mock()
    session_query.filter.return_value.first.return_value = session
    turn_query.filter.return_value.first.return_value = None
    db.query.side_effect = lambda model: session_query if model is ChatSession else turn_query
    db.execute.return_value.rowcount = 1
    response = {"status": "ok", "reply": "fixture", "items": [], "request_id": "request",
                "active_constraints": SessionState(runtime_max=90).model_dump(), "state_version": 3,
                "parser_mode": "fixture", "trace": {"total_ms": 1}, "degraded_components": [],
                "clarification": None}
    run = AsyncMock(return_value=response)
    monkeypatch.setattr(orchestrator, "run_turn", run)
    import redis
    cache = Mock()
    monkeypatch.setattr(redis.Redis, "from_url", Mock(return_value=cache))
    return SimpleNamespace(db=db, session=session, session_query=session_query, turn_query=turn_query,
                           response=response, run=run, cache=cache, user=SimpleNamespace(user_id=7),
                           request=MessageRequest(message="90分钟以内", client_message_id="message-123",
                                                  expected_state_version=2, top_k=2))


async def invoke(env):
    return await orchestrator.process_message(env.db, env.user, "session", env.request)


async def test_session_authorization_precedes_graph(boundary):
    env = boundary
    env.session_query.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as caught:
        await invoke(env)
    assert caught.value.status_code == 404
    env.run.assert_not_awaited()
    env.db.commit.assert_not_called()
    filters = env.session_query.filter.call_args.args
    assert str(filters[0]) == "chat_sessions.session_id = :session_id_1"
    assert str(filters[1]) == "chat_sessions.user_id = :user_id_1"


async def test_duplicate_message_replays_without_graph_or_write(boundary):
    env = boundary
    env.turn_query.filter.return_value.first.return_value = SimpleNamespace(
        user_text=env.request.message, top_k=env.request.top_k, response_json=env.response)
    assert await invoke(env) == env.response
    env.run.assert_not_awaited()
    env.db.execute.assert_not_called()
    env.db.commit.assert_not_called()


async def test_duplicate_message_id_with_changed_content_is_rejected(boundary):
    env = boundary
    env.turn_query.filter.return_value.first.return_value = SimpleNamespace(
        user_text="other message", top_k=2, response_json=env.response)
    with pytest.raises(HTTPException) as caught:
        await invoke(env)
    assert caught.value.status_code == 409
    env.run.assert_not_awaited()


async def test_stale_version_is_rejected_before_graph(boundary):
    env = boundary
    env.session.state_version = 3
    with pytest.raises(HTTPException) as caught:
        await invoke(env)
    assert caught.value.status_code == 409
    env.run.assert_not_awaited()
    env.db.commit.assert_not_called()


async def test_success_uses_original_conditional_update_and_one_turn_insert(boundary):
    env = boundary
    assert await invoke(env) == env.response
    assert env.db.commit.call_count == 2  # Release read transaction, then atomic business commit.
    env.db.add.assert_called_once()
    turn = env.db.add.call_args.args[0]
    assert isinstance(turn, ChatTurn)
    assert turn.client_message_id == env.request.client_message_id
    assert turn.response_json is env.response
    statement = env.db.execute.call_args.args[0]
    assert "chat_sessions.user_id =" in str(statement)
    assert "chat_sessions.state_version =" in str(statement)
    assert statement.compile().params["state_json"]["runtime_max"] == 90
    assert statement.compile().params["state_version"] == 3
    assert env.run.await_args.args[1].session_id == "session"
    env.cache.setex.assert_called_once()


async def test_lost_version_race_rolls_back_without_turn_insert(boundary):
    env = boundary
    env.db.execute.return_value.rowcount = 0
    with pytest.raises(HTTPException) as caught:
        await invoke(env)
    assert caught.value.status_code == 409
    env.db.rollback.assert_called_once()
    env.db.add.assert_not_called()
    env.cache.setex.assert_not_called()
    assert env.db.commit.call_count == 1


async def test_concurrent_duplicate_insert_recovers_saved_response(boundary):
    env = boundary
    saved = SimpleNamespace(user_text=env.request.message, top_k=env.request.top_k,
                            response_json={**env.response, "request_id": "winning-request"})
    env.turn_query.filter.return_value.first.side_effect = [None, saved]
    env.db.commit.side_effect = [None, IntegrityError("insert", {}, Exception("duplicate"))]
    result = await invoke(env)
    assert result["request_id"] == "winning-request"
    env.db.rollback.assert_called_once()
    env.cache.setex.assert_not_called()


async def test_failed_turn_does_not_commit_business_state(boundary):
    env = boundary
    original = deepcopy(env.session.state_json)
    env.run.side_effect = HTTPException(504, "timeout")
    with pytest.raises(HTTPException) as caught:
        await invoke(env)
    assert caught.value.status_code == 504
    env.db.execute.assert_not_called()
    env.db.add.assert_not_called()
    assert env.session.state_json == original
    assert env.db.commit.call_count == 1
