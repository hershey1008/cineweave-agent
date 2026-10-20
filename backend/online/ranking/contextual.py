def rank_signal(values):
    ordered = sorted(values, key=lambda mid: (-values[mid], mid))
    size = len(ordered)
    return {mid: (size - rank) / max(size, 1) for rank, mid in enumerate(ordered)}


def contextual_rank(candidates, semantic_scores, preference_scores, use_preference):
    sem = rank_signal({c["movie_id"]: semantic_scores.get(str(c["movie_id"]), -1) for c in candidates}) if semantic_scores else {}
    pref = rank_signal(preference_scores) if use_preference and preference_scores else {}
    fusion = rank_signal({c["movie_id"]: c["fusion_score"] for c in candidates})
    weights = (0.6, 0.3, 0.1) if pref and sem else ((0.85, 0, 0.15) if sem else (0, 0.8 if pref else 0, 0.2 if pref else 1))
    for candidate in candidates:
        mid = candidate["movie_id"]
        candidate["semantic_score"] = semantic_scores.get(str(mid))
        candidate["preference_score"] = preference_scores.get(mid) if pref else None
        candidate["final_score"] = sum(w * signal.get(mid, 0) for w, signal in zip(weights, (sem, pref, fusion)))
    return sorted(candidates, key=lambda c: (-c["final_score"], c["movie_id"])), weights
