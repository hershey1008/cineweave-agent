import asyncio
import json

import httpx
import pytest

from app.agent import llm_client
from app.agent.llm_client import LLMClient, LLMServiceError
from app.agent.schemas import SessionState


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'test-secret-never-forward')
    monkeypatch.setenv('LLM_MODEL', 'test-model')
    monkeypatch.setenv('LLM_BASE_URL', 'https://provider.example/v1')
    monkeypatch.delenv('LLM_TIMEOUT_SECONDS', raising=False)
    original = httpx.AsyncClient
    def install(handler):
        monkeypatch.setattr(llm_client.httpx, 'AsyncClient',
            lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return install


def completion(content, tokens=7):
    return httpx.Response(200, json={'choices':[{'message':{'content':content}}],
                                   'usage':{'total_tokens':tokens}})


@pytest.mark.asyncio
async def test_default_budget_and_one_call(remote):
    async def handler(request):
        assert request.extensions['timeout']['read'] == 45
        assert request.extensions['timeout']['connect'] == 5
        return completion(json.dumps({'set_fields':{'semantic_query':'lighthearted space exploration'}}))
    remote(handler)
    patch, trace = await LLMClient().parse('轻松一点，其他要求不变', SessionState(runtime_max=120))
    assert patch.set_fields['semantic_query'] == 'lighthearted space exploration'
    assert trace['calls'] == 1 and trace['tokens'] == 7
    assert trace['timeout_seconds'] == 45


@pytest.mark.asyncio
async def test_repair_shares_one_deadline(remote, monkeypatch):
    calls, budgets = [], []
    original_timeout = asyncio.timeout
    def deadline(seconds):
        budgets.append(seconds)
        return original_timeout(seconds)
    monkeypatch.setattr(llm_client.asyncio, 'timeout', deadline)
    async def handler(request):
        calls.append(request)
        return completion('invalid JSON' if len(calls)==1 else '{}')
    remote(handler)
    _, trace = await LLMClient().parse('轻松一点',SessionState())
    assert len(calls) == trace['calls'] == 2
    assert trace['tokens'] == 14 and budgets == [45]


@pytest.mark.asyncio
async def test_read_timeout_is_specific_and_not_retried(remote):
    calls = []
    async def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('provider secret detail',request=request)
    remote(handler)
    with pytest.raises(LLMServiceError) as caught:
        await LLMClient().parse('轻松一点', SessionState())
    assert len(calls) == 1
    assert caught.value.kind == 'timeout' and caught.value.status_code == 504
    assert '45' in str(caught.value) and 'secret' not in str(caught.value)


@pytest.mark.asyncio
async def test_total_deadline_cancels_inflight_request(remote, monkeypatch):
    original_timeout=asyncio.timeout
    monkeypatch.setattr(llm_client.asyncio, 'timeout', lambda seconds: original_timeout(0.01))
    async def handler(request):
        await asyncio.sleep(10)
        return completion('{}')
    remote(handler)
    with pytest.raises(LLMServiceError) as caught:
        await LLMClient().parse('轻松一点',SessionState())
    assert caught.value.kind == 'timeout'


@pytest.mark.asyncio
@pytest.mark.parametrize('status,kind', [(401,'authentication'),(403,'authentication'),
    (429,'rate_limit'),(400,'configuration'),(404,'configuration'),(422,'configuration'),(500,'provider')])
async def test_provider_errors_do_not_expose_body(remote, status, kind):
    remote(lambda request: httpx.Response(status,json={'error':'test-secret-never-forward'}))
    with pytest.raises(LLMServiceError) as caught:
        await LLMClient().parse('轻松一点',SessionState())
    assert caught.value.kind == kind
    assert 'test-secret' not in str(caught.value)


@pytest.mark.asyncio
async def test_connection_error_is_actionable(remote):
    def handler(request):
        raise httpx.ConnectError('private upstream details',request=request)
    remote(handler)
    with pytest.raises(LLMServiceError) as caught:
        await LLMClient().parse('轻松一点',SessionState())
    assert caught.value.kind == 'connection'
    assert 'private' not in str(caught.value)


@pytest.mark.asyncio
async def test_incompatible_response_is_specific(remote):
    remote(lambda request: httpx.Response(200,json={'unexpected':True}))
    with pytest.raises(LLMServiceError) as caught:
        await LLMClient().parse('轻松一点',SessionState())
    assert caught.value.kind == 'protocol' and caught.value.status_code == 502


@pytest.mark.asyncio
async def test_invalid_intent_has_only_one_repair(remote):
    calls=[]
    def handler(request):
        calls.append(request)
        return completion('not JSON')
    remote(handler)
    with pytest.raises(LLMServiceError) as caught:
        await LLMClient().parse('轻松一点',SessionState())
    assert caught.value.kind == 'invalid_output' and len(calls)==2
