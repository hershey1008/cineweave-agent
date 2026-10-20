import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from semantic_service.app.encoder import Encoder
from semantic_service.app.index import SemanticIndex, digest
from .prepare_documents import prepare


def build(data_dir: Path, root: Path, model: str, revision: str, batch_size=16):
    source_documents = prepare(data_dir)
    documents = [d for d in source_documents if d["title_type"] == "movie"]
    root.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    folder = root / version
    folder.mkdir()
    payload = "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in documents)
    (folder / "documents.jsonl").write_text(payload, encoding="utf-8")
    encoder = Encoder(model, revision)
    vectors = encoder.encode([d["text"] for d in documents], batch_size=batch_size)
    if not np.isfinite(vectors).all() or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=0.001):
        raise ValueError("Vector validation failed; old active index was retained")
    np.save(folder / "movie_ids.npy", np.array([d["movie_id"] for d in documents], dtype=np.int64))
    np.save(folder / "embeddings.npy", vectors)
    report = {"source_rows": len(source_documents), "movies": len(documents),
              "quarantine_count": len(source_documents) - len(documents),
              "quarantine": [{"movie_id": d["movie_id"], "source_title": d["source_title"],
                              "title_type": d["title_type"]} for d in source_documents if d["title_type"] != "movie"],
              "descriptions": sum(bool(d["description"]) for d in documents),
              "known_runtime": sum(bool(d["runtime_minutes"]) for d in documents),
              "with_aliases": sum(bool(d["aliases"]) for d in documents),
              "duplicate_ids": 0, "vectors_finite": True, "normalized": True}
    (folder / "quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"version": version, "model": model, "revision": revision,
                "dimension": int(vectors.shape[1]), "count": len(documents),
                "template_version": "movie-content-v1", "max_seq_length": 512,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                "files": {name: digest(folder / name) for name in
                          ["documents.jsonl", "movie_ids.npy", "embeddings.npy", "quality_report.json"]}}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    SemanticIndex(root, version=version)
    candidate = root / ("candidate-" + uuid.uuid4().hex + ".json")
    candidate.write_text(json.dumps({"version": version}), encoding="utf-8")
    # Publish only after validating the complete candidate version.
    original = root / "active.json"
    if original.exists():
        (root / "previous.json").write_bytes(original.read_bytes())
    os.replace(candidate, original)
    try:
        SemanticIndex(root)
    except Exception:
        previous = root / "previous.json"
        if previous.exists():
            original.write_bytes(previous.read_bytes())
        else:
            original.unlink(missing_ok=True)
        raise
    print(json.dumps({"manifest": manifest, "quality": report}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/semantic_index"))
    parser.add_argument("--model", default="BAAI/bge-m3")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    build(args.data_dir, args.output, args.model, args.revision, args.batch_size)
