import html
import re

import pandas as pd


def clean(value):
    if value is None or pd.isna(value):
        return ""
    text = html.unescape(str(value)).strip()
    if text.lower() in {"", "nan", "none", "null", "\\n"}:
        return ""
    return re.sub(r"\s+", " ", text)


def number(value):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def prepare(data_dir):
    df = pd.read_pickle(data_dir / "movies.pkl")
    metadata = pd.read_pickle(data_dir / "movie_metadata.pkl")
    aliases = {}
    for row in metadata["title_akas"].itertuples():
        if row.region in {"CN", "TW", "HK"} or row.language in {"zh", "cmn", "yue"}:
            title = clean(row.title)
            if title:
                aliases.setdefault(str(row.tconst), []).append(title)
    documents = []
    for row in df.to_dict("records"):
        imdb = clean(row.get("imdb_id"))
        title = clean(row.get("originalTitle")) or clean(row.get("title"))
        local_names = list(dict.fromkeys(aliases.get(imdb, [])))[:8]
        synopsis = clean(row.get("description"))
        genres = clean(row.get("genres")).split("|")
        year = number(row.get("startYear"))
        text = "\n".join([f"Title: {title}", f"Alternative titles: {'; '.join(local_names)}",
                           f"Year: {year or 'unknown'}", f"Genres: {', '.join(genres)}",
                           f"Synopsis: {synopsis}"])
        documents.append({"movie_id": int(row["movie_id"]), "title": title,
                          "source_title": clean(row.get("title")), "title_type": clean(row.get("titleType")),
                          "aliases": local_names, "imdb_id": imdb, "year": year,
                          "genres": genres, "runtime_minutes": number(row.get("runtimeMinutes")),
                          "description": synopsis, "text": text,
                          "quality": "full" if synopsis else "basic"})
    if len({d["movie_id"] for d in documents}) != len(documents):
        raise ValueError("Duplicate movie IDs in source")
    return documents
