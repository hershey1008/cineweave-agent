import hashlib
import json
from pathlib import Path

import numpy as np


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class SemanticIndex:
    def __init__(self, root: Path, version: str | None = None):
        active = {"version": version} if version else json.loads((root / "active.json").read_text(encoding="utf-8"))
        self.path = (root / active["version"]).resolve()
        if self.path.parent != root.resolve():
            raise ValueError("Invalid index version path")
        self.manifest = json.loads((self.path / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in self.manifest["files"].items():
            if Path(name).name != name or digest(self.path / name) != expected:
                raise ValueError(f"Index integrity check failed: {name}")
        self.ids = np.load(self.path / "movie_ids.npy", allow_pickle=False)
        self.vectors = np.load(self.path / "embeddings.npy", allow_pickle=False)
        if len(self.ids) != len(set(self.ids.tolist())):
            raise ValueError("Duplicate movie IDs")
        if self.vectors.shape != (len(self.ids), self.manifest["dimension"]):
            raise ValueError("Invalid vector shape")
        if not np.isfinite(self.vectors).all():
            raise ValueError("Non-finite vectors")
        if not np.allclose(np.linalg.norm(self.vectors, axis=1), 1, atol=0.001):
            raise ValueError("Unnormalized vectors")
        self.offset = {int(mid): i for i, mid in enumerate(self.ids)}

    def search(self, query_vector, eligible_ids: list[int], top_k: int):
        pairs = [(int(mid), self.offset[int(mid)]) for mid in set(eligible_ids)
                 if int(mid) in self.offset]
        pairs.sort()
        if not pairs:
            return [], {}
        ids, positions = zip(*pairs)
        scores = self.vectors[list(positions)] @ query_vector
        order = np.argsort(-scores, kind="stable")[:top_k]
        result = [{"movie_id": ids[int(i)], "score": float(scores[i])} for i in order]
        return result, {str(mid): float(score) for mid, score in zip(ids, scores)}
