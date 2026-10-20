import re
from collections import Counter

from sqlalchemy import func

from app.models import Movie, Rating, TitleAka


def movie_facts(db, movie_ids=None):
    query = db.query(Movie)
    if movie_ids is not None:
        if not movie_ids:
            return {}
        query = query.filter(Movie.movie_id.in_(movie_ids))
    return {m.movie_id: {"movie_id": m.movie_id, "title": m.title, "imdb_id": m.imdb_id,
        "year": m.year, "genres": m.genres or [], "runtime_minutes": m.runtime_minutes,
        "title_type": m.title_type,
        "description": m.description or "", "imdb_rating": m.imdb_rating,
        "avg_rating": m.avg_rating, "rating_count": m.rating_count or 0,
        "isAdult": m.is_adult or 0} for m in query.all()}


def resolve_titles(db, titles):
    ids = []
    for title in titles:
        name = re.sub(r"\s*[（(]\d{4}[)）]$", "", title).strip()
        match_year = re.search(r"[（(](\d{4})[)）]$", title)
        aliases = db.query(TitleAka.tconst).filter(func.lower(TitleAka.title) == name.lower())
        query = db.query(Movie).filter(Movie.title_type == "movie").filter((func.lower(Movie.title) == name.lower()) | Movie.imdb_id.in_(aliases))
        if match_year:
            query = query.filter(Movie.year == int(match_year.group(1)))
        movies = query.limit(3).all()
        if not movies:
            raise ValueError(f"当前电影库没有找到《{title}》。请换一部库内参考片，或直接描述主题；本目录主要为 2000 年及以前电影。")
        if len(movies) != 1:
            raise ValueError(f"《{title}》存在多个匹配，请补充年份。")
        ids.append(movies[0].movie_id)
    return ids


def user_context(db, user):
    history = db.query(Rating.movie_id).filter(Rating.user_id == user.user_id).order_by(Rating.timestamp.desc()).all()
    ids = [int(row[0]) for row in history]
    genres = Counter(g for row in db.query(Movie.genres).filter(Movie.movie_id.in_(ids[:30])).all()
                     for g in (row[0] or []))
    features = {"user_id": user.user_id, "gender": user.gender, "age": user.age,
                "occupation": user.occupation, "zip_code": user.zip_code,
                "preferred_genres": user.preferred_genres or [], "hist_movie_ids": ids[:50],
                "frequent_genres": list(dict.fromkeys((user.preferred_genres or []) + [g for g, _ in genres.most_common(3)]))}
    return features, set(ids)
