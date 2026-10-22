from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from elasticsearch import Elasticsearch
from redis.exceptions import ConnectionError, TimeoutError


@pytest.fixture
def recall_env(monkeypatch):
    # ElasticsearchService probes on import; unit tests must never contact a server.
    monkeypatch.setattr(Elasticsearch, "ping", lambda self: False)
    from online.recall import trending

    client = Mock()
    client.hget.return_value = "Action,Comedy"
    factory = Mock(return_value=client)
    monkeypatch.setattr(trending.redis.Redis, "from_url", factory)
    es = Mock(INDEX_NAME="movies")
    es.is_available.return_value = True
    es.client.search.return_value = {"hits": {"hits": [
        {"_source": {"movie_id": 42, "title": "Example", "genres": ["Action"]}}
    ]}}
    monkeypatch.setattr(trending, "es_service", es)
    return SimpleNamespace(
        module=trending, strategy=trending.UserPreferenceRecallStrategy(),
        client=client, factory=factory, es=es,
    )


@pytest.mark.parametrize("user_id", [7, "7"])
@pytest.mark.parametrize("context_genres", [None, [], ""])
async def test_reads_existing_profile_when_context_has_no_preferences(
    recall_env, user_id, context_genres
):
    env = recall_env
    env.client.hget.return_value = " Action, Comedy, , Sci-Fi ,"
    context = {"user_id": user_id}
    if context_genres is not None:
        context["frequent_genres"] = context_genres
    original = deepcopy(context)

    result = await env.strategy.recall(context, 6)

    assert env.client.mock_calls == [call.hget("user:7:profile", "frequent_genres")]
    env.es.client.search.assert_called_once_with(
        index="movies",
        query={"bool": {
            "must": [{"terms": {"genres": ["Action", "Comedy", "Sci-Fi"]}}],
            "filter": [{"range": {"avg_rating": {"gte": 5}}}],
        }},
        sort=[{"year": {"order": "desc"}}, {"avg_rating": {"order": "desc"}}],
        size=6,
        _source=["movie_id", "title", "genres"],
    )
    assert result == [{
        "movie_id": 42, "score": 0.8, "recall_type": "user_preference",
        "title": "Example", "genres": ["Action"],
    }]
    assert context == original


@pytest.mark.parametrize("genres", [["Drama"], " Drama, , Romance "])
async def test_context_preferences_take_priority_without_reading_redis(recall_env, genres):
    env = recall_env
    env.client.hget.side_effect = ConnectionError("offline")
    context = {"user_id": 7, "frequent_genres": genres}
    original = deepcopy(context)

    assert await env.strategy.recall(context, 3)

    env.client.hget.assert_not_called()
    expected = ["Drama"] if isinstance(genres, list) else ["Drama", "Romance"]
    assert env.es.client.search.call_args.kwargs["query"]["bool"]["must"] == [
        {"terms": {"genres": expected}}
    ]
    assert context == original


@pytest.mark.parametrize("profile_genres", [None, "", " , , "])
async def test_missing_or_empty_profile_skips_channel(recall_env, profile_genres):
    env = recall_env
    env.client.hget.return_value = profile_genres

    assert await env.strategy.recall({"user_id": 7}, 5) == []

    env.client.hget.assert_called_once_with("user:7:profile", "frequent_genres")
    env.es.client.search.assert_not_called()


@pytest.mark.parametrize("context", [{}, {"user_id": None}, {"preferred_genres": ["Action"]}])
async def test_missing_user_id_skips_redis(recall_env, context):
    env = recall_env

    assert await env.strategy.recall(context, 5) == []

    env.client.hget.assert_not_called()
    env.es.client.search.assert_not_called()


@pytest.mark.parametrize("error", [ConnectionError("offline"), TimeoutError("timeout")])
async def test_redis_failure_returns_empty_and_next_request_can_recover(recall_env, error):
    env = recall_env
    env.client.hget.side_effect = error

    assert await env.strategy.recall({"user_id": 7}, 5) == []
    env.es.client.search.assert_not_called()

    env.client.hget.side_effect = None
    assert await env.strategy.recall({"user_id": 7}, 5)


async def test_redis_initialization_failure_preserves_context_recall(recall_env):
    env = recall_env
    env.factory.side_effect = ValueError("invalid Redis URL")
    strategy = env.module.UserPreferenceRecallStrategy()

    assert strategy.redis_client is None
    assert await strategy.recall({"user_id": 7}, 5) == []
    env.es.client.search.assert_not_called()
    assert await strategy.recall({"user_id": 7, "frequent_genres": ["Drama"]}, 5)


async def test_unavailable_elasticsearch_skips_redis_and_search(recall_env):
    env = recall_env
    env.es.is_available.return_value = False

    assert await env.strategy.recall({"user_id": 7}, 5) == []

    env.client.hget.assert_not_called()
    env.es.client.search.assert_not_called()


async def test_elasticsearch_search_failure_returns_empty(recall_env):
    env = recall_env
    env.es.client.search.side_effect = RuntimeError("search failed")

    assert await env.strategy.recall({"frequent_genres": ["Drama"]}, 5) == []


async def test_no_elasticsearch_hits_returns_empty(recall_env):
    env = recall_env
    env.es.client.search.return_value = {"hits": {"hits": []}}

    assert await env.strategy.recall({"user_id": 7}, 5) == []


def test_redis_uses_existing_settings_and_decoded_responses(recall_env):
    env = recall_env
    env.factory.assert_called_once_with(
        env.module.settings.redis_url, decode_responses=True,
        socket_timeout=0.3, socket_connect_timeout=0.3,
    )
