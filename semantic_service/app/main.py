import json
import os
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .encoder import Encoder
from .index import SemanticIndex

resources = {}
cache = OrderedDict()
cache_lock = Lock()


@asynccontextmanager
async def lifespan(app):
    try:
        index = SemanticIndex(Path(os.getenv("SEMANTIC_INDEX_ROOT", "artifacts/semantic_index")))
        encoder = Encoder(index.manifest["model"], index.manifest["revision"])
        encoder.encode(["movie recommendation warmup"])
        resources.update(index=index, encoder=encoder, error=None)
    except Exception as exc:
        resources.update(error=type(exc).__name__ + ": " + str(exc))
    yield


app = FastAPI(title="CineWeave Semantic Service", lifespan=lifespan)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    eligible_ids: list[int] = Field(max_length=20000)
    top_k: int = Field(default=100, ge=1, le=1000)
    expected_version: str | None = None


@app.get("/health")
def health():
    index = resources.get("index")
    return {"ready": bool(index and resources.get("encoder")),
            "error": resources.get("error"),
            "manifest": index.manifest if index else None}


@app.post("/search")
def search(request: SearchRequest):
    if not resources.get("encoder"):
        raise HTTPException(503, "Semantic encoder/index is not ready")
    started = time.perf_counter()
    index = resources["index"]
    if request.expected_version and request.expected_version != index.manifest["version"]:
        raise HTTPException(409, "Semantic index version mismatch")
    text = " ".join(request.text.split())
    with cache_lock:
        vector = cache.get(text)
        hit = vector is not None
    if vector is None:
        vector = resources["encoder"].encode([text])[0]
        with cache_lock:
            cache[text] = vector
            cache.move_to_end(text)
            while len(cache) > 256:
                cache.popitem(last=False)
    encode_ms = (time.perf_counter() - started) * 1000
    items, scores = index.search(vector, request.eligible_ids, request.top_k)
    return {"items": items, "scores": scores, "version": index.manifest["version"],
            "model": index.manifest["model"], "cache_hit": hit,
            "encode_ms": round(encode_ms, 2),
            "total_ms": round((time.perf_counter() - started) * 1000, 2)}
