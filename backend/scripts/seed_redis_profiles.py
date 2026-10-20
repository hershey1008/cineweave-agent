"""Populate CineWeave's dedicated Redis from the local historical snapshot."""
import os
from collections import Counter
from pathlib import Path

import pandas as pd
import redis

from app.config import settings


def main():
    root = Path(os.getenv("DATA_DIR", "/data"))
    users = pd.read_pickle(root / "users.pkl")
    movies = pd.read_pickle(root / "movies.pkl")
    ratings = pd.read_pickle(root / "ratings.pkl").sort_values("timestamp", ascending=False)
    genres = {int(r["movie_id"]): str(r["genres"]).split("|") for r in movies.to_dict("records")}
    histories = {int(uid): frame.movie_id.astype(int).tolist()[:50] for uid, frame in ratings.groupby("user_id", sort=False)}
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    pipe = client.pipeline()
    for index, row in enumerate(users.to_dict("records"), 1):
        uid = int(row["user_id"])
        history = histories.get(uid, [])
        counts = Counter(g for mid in history for g in genres.get(mid, []))
        profile = {field: str(row[field]) for field in ["gender", "age", "occupation", "zip_code"]}
        profile["frequent_genres"] = ",".join(g for g, _ in counts.most_common(3))
        pipe.hset(f"user:{uid}:profile", mapping=profile)
        if history:
            pipe.delete(f"user:{uid}:history")
            pipe.rpush(f"user:{uid}:history", *history)
        if index % 200 == 0:
            pipe.execute()
    pipe.execute()
    print({"profiles": len(users), "historical_users": len(histories), "scope": "dedicated CineWeave Redis"})


if __name__ == "__main__":
    main()
