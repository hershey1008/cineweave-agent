GENRE_CN = {"Sci-Fi": "科幻", "Comedy": "喜剧", "Horror": "恐怖", "Mystery": "悬疑",
            "Thriller": "惊悚", "Animation": "动画", "Romance": "爱情", "Action": "动作",
            "Adventure": "冒险", "Fantasy": "奇幻", "Crime": "犯罪", "War": "战争",
            "Documentary": "纪录", "Children's": "儿童", "Drama": "剧情", "Western": "西部"}


def explain(movie, candidate, state):
    evidence = []
    if movie.get("runtime_minutes"):
        evidence.append({"field": "runtime_minutes", "value": movie["runtime_minutes"]})
    if movie.get("year"):
        evidence.append({"field": "year", "value": movie["year"]})
    evidence.append({"field": "genres", "value": movie["genres"]})
    if movie.get("description"):
        evidence.append({"field": "description", "value": movie["description"][:300]})
    reasons = []
    if "semantic" in candidate.get("recall_sources", []):
        reasons.append("内容语义与你本次需求相近")
    if "item_based" in candidate.get("recall_sources", []):
        reasons.append("与历史交互电影有关联")
    if state.include_genres:
        reasons.append("符合" + "、".join(GENRE_CN.get(g, g) for g in state.include_genres) + "类型要求")
    if state.runtime_max and movie.get("runtime_minutes"):
        reasons.append(f"片长 {movie['runtime_minutes']} 分钟，符合时长限制")
    if not reasons:
        reasons.append("根据电影口碑与当前偏好选出")
    return "；".join(reasons) + "。", evidence
