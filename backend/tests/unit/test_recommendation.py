import pytest

from app.agent.schemas import SessionState
from app.agent.explanation_service import explain
from online.filtering import satisfies
from online.recall.fusion import fuse
from online.ranking.contextual import contextual_rank
from online.reranking.contextual import diversify

BASE = {"movie_id": 7, "year": 1999, "runtime_minutes": 110, "genres": ["Sci-Fi", "Action"]}


@pytest.mark.parametrize("changes,state,seen,expected", [
    ({}, {"runtime_max": 120}, set(), True),
    ({"runtime_minutes": None}, {"runtime_max": 120}, set(), False),
    ({"runtime_minutes": 0}, {"runtime_max": 120}, set(), False),
    ({"runtime_minutes": 121}, {"runtime_max": 120}, set(), False),
    ({"year": None}, {"year_min": 1990}, set(), False),
    ({}, {"year_max": 1990}, set(), False),
    ({}, {"include_genres": ["Sci-Fi", "Comedy"]}, set(), False),
    ({}, {"exclude_genres": ["Action"]}, set(), False),
    ({}, {"excluded_movie_ids": [7]}, set(), False),
    ({}, {"reference_movie_ids": [7]}, set(), False),
    ({}, {}, {7}, False),
    ({}, {"exclude_seen": False}, {7}, True),
    ({}, {"year_min": 1999, "year_max": 1999}, set(), True),
    ({"title_type": "tvSeries"}, {}, set(), False),
    ({"title_type": "videoGame"}, {}, set(), False),
    ({"title_type": "movie"}, {}, set(), True),
])
def test_hard_filters(changes, state, seen, expected):
    assert satisfies({**BASE, **changes}, SessionState(**state), seen) is expected


def test_fusion_deduplicates_and_retains_all_sources():
    items = fuse({"semantic": [{"movie_id": 1}, {"movie_id": 1}], "i2i": [{"movie_id": 1}, {"movie_id": 2}]})
    assert len(items) == 2
    a = next(c for c in items if c["movie_id"] == 1)
    assert a["recall_sources"] == ["semantic", "i2i"]
    assert a["fusion_score"] == pytest.approx(2 / 61)


def test_semantic_quota_survives_busy_other_channels():
    semantic = [{"movie_id": 100 + i} for i in range(40)]
    others = [{"movie_id": i} for i in range(100)]
    result = fuse({"semantic": semantic, **{str(i): others for i in range(8)}}, limit=50)
    assert set(range(100, 140)) <= {c["movie_id"] for c in result}
    assert len(result) == 50


def test_cold_user_does_not_use_deepfm_scores():
    candidates = [{"movie_id": 1, "fusion_score": 1}, {"movie_id": 2, "fusion_score": .5}]
    result, weights = contextual_rank(candidates, {"1": .9, "2": .1}, {1: .1, 2: .99}, False)
    assert result[0]["movie_id"] == 1
    assert weights[1] == 0
    assert all(c["preference_score"] is None for c in result)


def test_missing_models_can_still_use_fusion_without_claiming_probability():
    result, weights = contextual_rank([{"movie_id": 9, "fusion_score": 1}], {}, {}, True)
    assert weights == (0, 0, 1)
    assert result[0]["final_score"] == 1


def test_explanation_numbers_come_from_facts():
    movie = {**BASE, "description": "A hacker questions reality."}
    reason, evidence = explain(movie, {"recall_sources": ["semantic"]}, SessionState(runtime_max=120))
    assert "110 分钟" in reason
    assert {"field": "runtime_minutes", "value": 110} in evidence
    assert "导演" not in reason


def test_diversity_can_choose_close_alternative_but_not_destroy_relevance():
    catalog = {1:{'genres':['Sci-Fi'],'year':1990},2:{'genres':['Sci-Fi'],'year':1991},
               3:{'genres':['Sci-Fi'],'year':1992},4:{'genres':['Comedy'],'year':1980}}
    candidates = [{'movie_id':1,'final_score':1},{'movie_id':2,'final_score':.99},
                  {'movie_id':3,'final_score':.98},{'movie_id':4,'final_score':.97}]
    assert [i['movie_id'] for i in diversify(candidates,catalog,3)] == [1,2,4]
    candidates[3]['final_score']=.1
    assert [i['movie_id'] for i in diversify(candidates,catalog,3)] == [1,2,3]
