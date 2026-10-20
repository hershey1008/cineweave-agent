import asyncio
import time
from types import SimpleNamespace

from app.agent.explanation_service import explain
from online.filtering import satisfies
from online.recall.fusion import fuse
from online.recall.semantic import semantic_recall
from online.ranking.contextual import contextual_rank
from online.reranking.contextual import diversify


async def recommend_context(context, catalog):
    started = time.perf_counter()
    state = context.state
    eligible = {mid: m for mid, m in catalog.items() if satisfies(m, state, context.seen_ids)}
    trace = {"catalog_count": len(catalog), "eligible_count": len(eligible), "channels": {},
             "degraded_components": [], "ranking": "contextual", "parser_mode": None}
    trace["filter_ms"] = round((time.perf_counter() - started) * 1000, 2)
    if not eligible:
        return [], trace
    channels = {}
    scores = {}
    if state.semantic_query:
        try:
            semantic = await semantic_recall(state.semantic_query, list(eligible), top_k=200)
            channels["semantic"] = semantic["items"]
            scores = semantic["scores"]
            trace["semantic"] = {k: semantic[k] for k in ["version", "model", "cache_hit", "encode_ms", "total_ms"]}
        except Exception as exc:
            trace["degraded_components"].append("semantic:" + type(exc).__name__)

    recall_started = time.perf_counter()
    if len(context.seen_ids) >= 5:
        try:
            from online.recall import get_recall_service
            service = get_recall_service()
            service.resource_manager._ensure_resources_loaded()
            if not service.movie_genre_map:
                service.set_movie_genre_map([SimpleNamespace(movie_id=mid, genres=m["genres"]) for mid, m in catalog.items()])
            strategies = list(service.strategies)
            outputs = await asyncio.gather(*(s.recall(dict(context.user_features), 200) for s in strategies), return_exceptions=True)
            names = ["youtubednn", "item_based", "genre_preference"]
            for name, output in zip(names, outputs):
                if isinstance(output, Exception):
                    trace["degraded_components"].append(name + ":" + type(output).__name__)
                else:
                    channels[name] = [c for c in output if int(c["movie_id"]) in eligible]
        except Exception as exc:
            trace["degraded_components"].append("collaborative:" + type(exc).__name__)
    else:
        try:
            from online.cold_start import get_cold_start_service
            cold = await get_cold_start_service().recommend(dict(context.user_features), top_k=100)
            channels["cold_start"] = [c for c in cold if int(c["movie_id"]) in eligible]
        except Exception as exc:
            trace["degraded_components"].append("cold_start:" + type(exc).__name__)

    trace["other_recall_ms"] = round((time.perf_counter() - recall_started) * 1000, 2)
    popular = sorted(eligible.values(), key=lambda m: (m["rating_count"], m.get("imdb_rating") or 0, -m["movie_id"]), reverse=True)
    channels["catalog_popular"] = [{"movie_id": m["movie_id"], "score": float(m["rating_count"])} for m in popular[:100]]
    trace["channels"] = {name: len(items) for name, items in channels.items()}
    fusion_started = time.perf_counter()
    candidates = fuse(channels, limit=200, semantic_quota=40)
    trace["fusion_ms"] = round((time.perf_counter() - fusion_started) * 1000, 2)
    preference = {}
    use_preference = len(context.seen_ids) >= 5
    preference_started = time.perf_counter()
    if use_preference:
        try:
            from online.ranking import get_ranking_service
            ranker = get_ranking_service()
            if not ranker.is_ready:
                raise RuntimeError("DeepFM not ready")
            feature_map = {mid: {"genres": m["genres"][0] if m["genres"] else None,
                "isAdult": m["isAdult"], "year": m["year"], "startYear": m["year"]} for mid, m in eligible.items()}
            ranked = await ranker.rank_with_item_features(dict(context.user_features), candidates, feature_map, top_k=None)
            if not ranked or any(c.get("score_source") != "deepfm" for c in ranked):
                raise RuntimeError("DeepFM prediction fell back to recall scores")
            preference = {int(c["movie_id"]): float(c["score"]) for c in ranked}
        except Exception as exc:
            trace["degraded_components"].append("deepfm:" + type(exc).__name__)
    trace["deepfm_ms"] = round((time.perf_counter() - preference_started) * 1000, 2)
    contextual_started = time.perf_counter()
    candidates, weights = contextual_rank(candidates, scores, preference, use_preference)
    selected = diversify(candidates, catalog, context.top_k)
    trace["reranking_strategies"] = ["bounded_genre", "bounded_decade"]
    cards = []
    for candidate in selected:
        movie = eligible[candidate["movie_id"]]
        if not satisfies(movie, state, context.seen_ids):
            continue
        reason, evidence = explain(movie, candidate, state)
        cards.append({**movie, **candidate, "reason": reason, "evidence": evidence,
                      "final_rank": len(cards) + 1, "poster_url": f"/api/posters/{movie['movie_id']}.png"})
    trace.update(candidate_count=len(candidates), weights=list(weights),
                 contextual_ms=round((time.perf_counter() - contextual_started) * 1000, 2),
                 ranking_ms=round((time.perf_counter() - started) * 1000, 2))
    return cards, trace
