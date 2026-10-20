"""One pinned multilingual encoder, shared by offline and online paths."""
import os
import threading
import hashlib
import json
from pathlib import Path

import numpy as np


class Encoder:
    def __init__(self, model_name: str, revision: str | None = None):
        local_path = os.getenv("EMBEDDING_MODEL_PATH")
        if local_path:
            folder = Path(local_path)
            metadata = json.loads((folder / "cineweave-model.json").read_text(encoding="utf-8"))
            if metadata["model"] != model_name or metadata["revision"] != revision:
                raise ValueError("Local encoder snapshot does not match the index model/revision")
            checksum = hashlib.sha256()
            with (folder / "pytorch_model.bin").open("rb") as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    checksum.update(block)
            if checksum.hexdigest() != metadata["weight_sha256"]:
                raise ValueError("Local encoder checksum mismatch")
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(int(os.getenv("EMBEDDING_THREADS", "4")))
        self.model = SentenceTransformer(local_path or model_name, revision=None if local_path else revision,
                                         device=os.getenv("EMBEDDING_DEVICE", "cpu"))
        self.model.max_seq_length = 512
        self.lock = threading.Lock()

    def encode(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        with self.lock:
            result = self.model.encode(texts, batch_size=batch_size,
                                       normalize_embeddings=True,
                                       convert_to_numpy=True,
                                       show_progress_bar=len(texts) > 100)
        return np.asarray(result, dtype=np.float32)
