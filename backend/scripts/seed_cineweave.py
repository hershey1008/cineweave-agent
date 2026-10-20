"""Seed a separate local CineWeave database; never resets existing data."""
import html
import io
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.database import Base, SessionLocal, engine
from app.models import (Genre, Movie, User, Rating, TitleAka, TitleCrew,
                        TitlePrincipal, NameBasics, TitleRating)
from app.core.security import get_password_hash


def value(v):
    if v is None or pd.isna(v) or str(v) in {"\\N", "nan", "None"}:
        return None
    return v


def integer(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def as_array(v, delimiter=","):
    return str(v).split(delimiter) if value(v) is not None else []


def bulk(db, model, mappings):
    if db.query(model).count():
        print(model.__tablename__, "already populated", flush=True)
        return
    for i in range(0, len(mappings), 3000):
        db.bulk_insert_mappings(model, mappings[i:i + 3000])
    print(model.__tablename__, len(mappings), flush=True)


def seed():
    Base.metadata.create_all(engine)
    root = Path(os.getenv("DATA_DIR", "/data"))
    db = SessionLocal()
    try:
        movies = pd.read_pickle(root / "movies.pkl")
        users = pd.read_pickle(root / "users.pkl")
        ratings = pd.read_pickle(root / "ratings.pkl")
        metadata = pd.read_pickle(root / "movie_metadata.pkl")
        bulk(db, User, [{"user_id": int(r["user_id"]), "gender": str(r["gender"]),
            "age": str(r["age"]), "occupation": str(r["occupation"]), "zip_code": str(r["zip_code"]),
            "is_active": 1, "is_superuser": 0, "preferred_genres": []} for r in users.to_dict("records")])
        aggregate = ratings.groupby("movie_id")["rating"].agg(["mean", "count"]).to_dict("index")
        bulk(db, Movie, [{"movie_id": int(r["movie_id"]), "imdb_id": str(r["imdb_id"]),
            "title": str(value(r.get("originalTitle")) or r["title"]),
            "year": integer(r.get("startYear")), "genres": as_array(r["genres"], "|"),
            "description": html.unescape(str(value(r.get("description")) or "")),
            "runtime_minutes": integer(r.get("runtimeMinutes")), "is_adult": integer(r.get("isAdult")) or 0,
            "imdb_rating": float(r["averageRating"]) if value(r.get("averageRating")) is not None else None,
            "imdb_votes": integer(r.get("numVotes")), "title_type": value(r.get("titleType")),
            "avg_rating": float(aggregate.get(r["movie_id"], {}).get("mean", 0)),
            "rating_count": int(aggregate.get(r["movie_id"], {}).get("count", 0))} for r in movies.to_dict("records")])
        db.commit()
        if db.query(Rating).count() == 0:
            raw = engine.raw_connection()
            try:
                buffer = io.StringIO()
                ratings[["user_id", "movie_id", "rating", "timestamp"]].astype("int64").to_csv(buffer, index=False, header=False)
                buffer.seek(0)
                cursor = raw.cursor()
                cursor.copy_expert("COPY ratings (user_id,movie_id,rating,timestamp) FROM STDIN WITH (FORMAT CSV)", buffer)
                raw.commit()
                print("ratings", len(ratings), flush=True)
            finally:
                raw.close()
        bulk(db, Genre, [{"name": g} for g in sorted({g for v in movies.genres for g in str(v).split("|")})])
        bulk(db, TitleAka, [{"tconst": r["tconst"], "ordering": int(r["ordering"]), "title": str(r["title"]),
            "region": value(r.get("region")), "language": value(r.get("language")), "types": value(r.get("types")),
            "attributes": value(r.get("attributes")), "is_original_title": integer(r.get("isOriginalTitle"))}
            for r in metadata["title_akas"].to_dict("records")])
        bulk(db, TitleCrew, [{"tconst": r["tconst"], "directors": as_array(r.get("directors")),
            "writers": as_array(r.get("writers"))} for r in metadata["title_crew"].to_dict("records")])
        bulk(db, NameBasics, [{"nconst": r["nconst"], "primary_name": r["primaryName"],
            "birth_year": integer(r.get("birthYear")), "death_year": integer(r.get("deathYear")),
            "primary_profession": as_array(r.get("primaryProfession")), "known_for_titles": as_array(r.get("knownForTitles"))}
            for r in metadata["name_basics"].to_dict("records")])
        bulk(db, TitlePrincipal, [{"tconst": r["tconst"], "ordering": int(r["ordering"]), "nconst": r["nconst"],
            "category": r["category"], "job": value(r.get("job")), "characters": value(r.get("characters"))}
            for r in metadata["title_principals"].to_dict("records")])
        bulk(db, TitleRating, [{"tconst": r["tconst"], "average_rating": float(r["averageRating"]),
            "num_votes": int(r["numVotes"])} for r in metadata["title_ratings"].to_dict("records")])
        db.commit()
        db.execute(text("SELECT setval(pg_get_serial_sequence('users','user_id'), (SELECT MAX(user_id) FROM users))"))
        password = get_password_hash(os.getenv("DEMO_PASSWORD", "CineweaveDemo!2026"))
        if not db.query(User).filter(User.email == "demo@cineweave.local").first():
            db.add(User(email="demo@cineweave.local", username="新朋友", hashed_password=password,
                        preferred_genres=["Sci-Fi"], gender="M", age="25", occupation="student", is_active=1, is_superuser=0))
        historical = db.query(User).filter(User.user_id == 1).first()
        if historical:
            historical.email = "history@cineweave.local"
            historical.username = "资深影迷"
            historical.hashed_password = password
            historical.preferred_genres = ["Sci-Fi", "Comedy"]
        db.commit()
        print({"movies": db.query(Movie).count(), "ratings": db.query(Rating).count(), "users": db.query(User).count()}, flush=True)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
