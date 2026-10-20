"""Bounded diversification: preserve relevance while avoiding long identical runs."""


def diversify(candidates, catalog, top_k, max_score_drop=0.08):
    selected, remaining = [], list(candidates)
    def genre(item):
        return tuple(catalog[item['movie_id']].get('genres', [])[:1])
    def decade(item):
        year = catalog[item['movie_id']].get('year')
        return year // 10 if year else None
    while remaining and len(selected) < top_k:
        choice = 0
        if len(selected) >= 2:
            same_genre = bool(genre(selected[-1])) and genre(selected[-1]) == genre(selected[-2]) == genre(remaining[0])
            same_decade = decade(selected[-1]) is not None and decade(selected[-1]) == decade(selected[-2]) == decade(remaining[0])
            if same_genre or same_decade:
                for i, item in enumerate(remaining[1:6], 1):
                    if item['final_score'] < remaining[0]['final_score'] - max_score_drop:
                        continue
                    if same_genre and genre(item) == genre(selected[-1]):
                        continue
                    if same_decade and decade(item) == decade(selected[-1]):
                        continue
                    choice = i
                    break
        selected.append(remaining.pop(choice))
    return selected
