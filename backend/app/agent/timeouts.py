"""Keep the outer chat deadline longer than the complete LLM budget."""
import math
import os


def seconds(name, default, maximum):
    try:
        value=float(os.getenv(name,str(default)))
    except ValueError:
        raise ValueError(f'{name} 必须是 1 到 {maximum} 之间的秒数') from None
    if not math.isfinite(value) or not 1 <= value <= maximum:
        raise ValueError(f'{name} 必须是 1 到 {maximum} 之间的秒数')
    return value


def llm_timeout_seconds():
    return seconds('LLM_TIMEOUT_SECONDS',45,120)


def chat_timeout_seconds():
    configured=seconds('CHAT_TIMEOUT',20,180)
    if os.getenv('LLM_API_KEY') and os.getenv('LLM_MODEL'):
        # Preserve old .env files: CHAT_TIMEOUT=20 cannot truncate the 45s LLM call.
        return max(configured,llm_timeout_seconds()+15)
    return configured
