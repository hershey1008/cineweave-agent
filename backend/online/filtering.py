def satisfies(movie, state, seen_ids):
    if "title_type" in movie and movie["title_type"] != "movie":
        return False
    mid = movie["movie_id"]
    if mid in state.reference_movie_ids:
        return False
    if mid in state.excluded_movie_ids or (state.exclude_seen and mid in seen_ids):
        return False
    genres = set(movie.get("genres") or [])
    if state.include_genres and not set(state.include_genres) <= genres:
        return False
    if genres & set(state.exclude_genres):
        return False
    year, runtime = movie.get("year"), movie.get("runtime_minutes")
    if state.year_min is not None and (year is None or year < state.year_min):
        return False
    if state.year_max is not None and (year is None or year > state.year_max):
        return False
    if state.runtime_max is not None and (runtime is None or runtime <= 0 or runtime > state.runtime_max):
        return False
    return True
