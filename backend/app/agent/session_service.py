from .schemas import IntentPatch, SessionState

ALLOWED = {"semantic_query", "include_genres", "exclude_genres", "year_min", "year_max",
           "runtime_max", "exclude_seen"}


def apply_patch(state: SessionState, patch: IntentPatch):
    if patch.action == "reset":
        return SessionState()
    if not set(patch.set_fields) <= ALLOWED or not set(patch.clear_fields) <= ALLOWED:
        raise ValueError("模型输出包含不允许修改的字段")
    values = state.model_dump()
    defaults = SessionState().model_dump()
    for name in patch.clear_fields:
        values[name] = defaults[name]
    values.update(patch.set_fields)
    if patch.action != "explain":
        for position in patch.exclude_positions:
            if position < 1 or position > len(state.last_recommendation_ids):
                raise ValueError("指定位置不在上轮推荐列表中，请说明要替换哪部电影")
            values["excluded_movie_ids"] = list(dict.fromkeys(
                values["excluded_movie_ids"] + [state.last_recommendation_ids[position - 1]]))
    return SessionState.model_validate(values)
