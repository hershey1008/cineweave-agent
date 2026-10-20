from dataclasses import dataclass, field

from app.agent.schemas import SessionState


@dataclass
class RecommendationContext:
    state: SessionState
    user_features: dict
    seen_ids: set[int]
    top_k: int = 10
    request_id: str = ""
    trace: dict = field(default_factory=dict)
