"""Request-scoped dependencies, kept outside serializable graph state."""

from dataclasses import dataclass, field
from typing import Any

from .llm_client import LLMClient
from .schemas import MessageRequest


@dataclass
class TurnRuntime:
    db: Any
    user: Any
    request: MessageRequest
    session_id: str
    request_id: str
    started: float
    version: int
    client: LLMClient
    node_events: list[dict] = field(default_factory=list)
