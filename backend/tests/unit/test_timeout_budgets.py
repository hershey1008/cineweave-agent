import pytest

from app.agent.timeouts import chat_timeout_seconds, llm_timeout_seconds


@pytest.fixture
def clean(monkeypatch):
    for name in ['LLM_API_KEY','LLM_MODEL','LLM_TIMEOUT_SECONDS','CHAT_TIMEOUT']:
        monkeypatch.delenv(name,raising=False)
    return monkeypatch


def test_rules_keeps_twenty_seconds(clean):
    assert chat_timeout_seconds()==20


def test_existing_env_cannot_truncate_llm(clean):
    clean.setenv('LLM_API_KEY','test-key')
    clean.setenv('LLM_MODEL','test-model')
    clean.setenv('CHAT_TIMEOUT','20')
    assert llm_timeout_seconds()==45
    assert chat_timeout_seconds()==60


def test_custom_outer_deadline_remains_supported(clean):
    clean.setenv('LLM_API_KEY','test-key')
    clean.setenv('LLM_MODEL','test-model')
    clean.setenv('CHAT_TIMEOUT','90')
    assert chat_timeout_seconds()==90


@pytest.mark.parametrize('invalid',['NaN','inf','0','121','invalid'])
def test_invalid_llm_deadline_rejected(clean,invalid):
    clean.setenv('LLM_TIMEOUT_SECONDS',invalid)
    with pytest.raises(ValueError):
        llm_timeout_seconds()
