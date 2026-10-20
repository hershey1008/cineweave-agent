def fuse(channels: dict[str, list[dict]], limit=200, semantic_quota=40):
    candidates = {}
    for name, items in channels.items():
        seen = set()
        for rank, item in enumerate(items, 1):
            mid = int(item["movie_id"])
            if mid in seen:
                continue
            seen.add(mid)
            candidate = candidates.setdefault(mid, {"movie_id": mid, "recall_sources": [],
                "channel_ranks": {}, "channel_scores": {}, "fusion_score": 0.0})
            candidate["recall_sources"].append(name)
            candidate["channel_ranks"][name] = rank
            candidate["channel_scores"][name] = float(item.get("score", 0))
            candidate["fusion_score"] += 1 / (60 + rank)
    ordered = sorted(candidates.values(), key=lambda c: (-c["fusion_score"], c["movie_id"]))
    protected = [c for c in ordered if c["channel_ranks"].get("semantic", 100000) <= semantic_quota]
    selected = {c["movie_id"] for c in protected[:limit]}
    for candidate in ordered:
        if len(selected) >= limit:
            break
        selected.add(candidate["movie_id"])
    return [c for c in ordered if c["movie_id"] in selected]
