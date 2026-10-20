from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GENRES = {"Action", "Adventure", "Animation", "Children's", "Comedy", "Crime", "Documentary",
          "Drama", "Fantasy", "Film-Noir", "Horror", "Musical", "Mystery", "Romance",
          "Sci-Fi", "Thriller", "War", "Western"}


class SessionState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semantic_query: str = Field(default="", max_length=2000)
    include_genres: list[str] = Field(default_factory=list)
    exclude_genres: list[str] = Field(default_factory=list)
    year_min: int | None = Field(default=None, ge=1888, le=2100)
    year_max: int | None = Field(default=None, ge=1888, le=2100)
    runtime_max: int | None = Field(default=None, ge=1, le=1440)
    exclude_seen: bool = True
    excluded_movie_ids: list[int] = Field(default_factory=list, max_length=10000)
    reference_movie_ids: list[int] = Field(default_factory=list, max_length=10)
    last_recommendation_ids: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("include_genres", "exclude_genres")
    @classmethod
    def genres_valid(cls, values):
        if not set(values) <= GENRES:
            raise ValueError("Unknown genre")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def consistent(self):
        if self.year_min and self.year_max and self.year_min > self.year_max:
            raise ValueError("年份范围冲突：起始年份晚于结束年份")
        if set(self.include_genres) & set(self.exclude_genres):
            raise ValueError("同一种类型同时被要求包含和排除")
        return self


class IntentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["recommend", "replace", "clarify", "explain", "reset"] = "recommend"
    set_fields: dict[str, Any] = Field(default_factory=dict)
    clear_fields: list[str] = Field(default_factory=list)
    exclude_positions: list[int] = Field(default_factory=list)
    reference_titles: list[str] = Field(default_factory=list, max_length=5)
    question: str | None = None


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1000)
    client_message_id: str = Field(min_length=8, max_length=80)
    expected_state_version: int = Field(ge=0)
    top_k: int = Field(default=10, ge=1, le=20)


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=8, max_length=80)
    request_id: str = Field(min_length=8, max_length=80)
    movie_id: int = Field(gt=0)
    feedback_type: Literal["like", "dislike", "seen"]


class EventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=8, max_length=80)
    session_id: str
    request_id: str
    movie_id: int = Field(gt=0)
    event_type: Literal["impression", "movie_open"]
