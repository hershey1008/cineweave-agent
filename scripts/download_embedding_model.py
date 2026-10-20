"""Download a pinned official BGE-M3 snapshot with a verified weight checksum."""
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
WEIGHT_SHA256 = "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38"
FILES = ["config.json", "config_sentence_transformers.json", "modules.json", "sentence_bert_config.json",
         "sentencepiece.bpe.model", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
         "1_Pooling/config.json", "pytorch_model.bin"]


def download_weight(target):
    size, block = 2271145830, 8 * 1024 * 1024
    chunks = target.parent / "weight_chunks"
    chunks.mkdir(exist_ok=True)
    def fetch(start):
        end = min(start + block, size) - 1
        path = chunks / str(start)
        if path.exists() and path.stat().st_size == end - start + 1:
            return path
        for attempt in range(4):
            try:
                url = f"https://huggingface.co/BAAI/bge-m3/resolve/{REVISION}/pytorch_model.bin?download=true&chunk={start}"
                with requests.get(url, headers={"Range": f"bytes={start}-{end}"}, stream=True, timeout=(15, 35)) as response:
                    response.raise_for_status()
                    if response.status_code != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {start}-"):
                        raise ValueError("Range response did not match the requested block")
                    received = 0
                    with path.open("wb") as output:
                        for data in response.iter_content(1024 * 1024):
                            received += len(data)
                            if received > end - start + 1:
                                raise ValueError("Range response exceeded the requested size")
                            output.write(data)
                    if received != end - start + 1:
                        raise ValueError("Incomplete model block")
                return path
            except (requests.RequestException, ValueError):
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)
    starts = list(range(0, size, block))
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = [pool.submit(fetch, start) for start in starts]
        for count, future in enumerate(as_completed(pending), 1):
            future.result()
            if count % 12 == 0 or count == len(starts):
                print("verified model blocks", count, "/", len(starts), flush=True)
    combined = target.with_suffix(".verified-download")
    with combined.open("wb") as output:
        for start in starts:
            with (chunks / str(start)).open("rb") as source:
                for data in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(data)
    if sha(combined) != WEIGHT_SHA256:
        raise ValueError("Combined model checksum mismatch")
    os.replace(combined, target)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    root = Path(os.getenv("EMBEDDING_MODEL_PATH", "artifacts/model_cache/bge-m3"))
    root.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and (name != "pytorch_model.bin" or sha(target) == WEIGHT_SHA256):
            print("verified/existing", name, flush=True)
            continue
        if name == "pytorch_model.bin":
            download_weight(target)
            continue
        part = target.with_suffix(target.suffix + ".part")
        start = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={start}-"} if start else {}
        url = f"https://huggingface.co/BAAI/bge-m3/resolve/{REVISION}/{name}?download=true"
        print("downloading", name, "resume_bytes", start, flush=True)
        with requests.get(url, headers=headers, stream=True, timeout=(15, 45)) as response:
            response.raise_for_status()
            append = bool(start and response.status_code == 206 and response.headers.get("Content-Range", "").startswith(f"bytes {start}-"))
            written = start if append else 0
            milestone = written // (100 * 1024 * 1024)
            with part.open("ab" if append else "wb") as f:
                for chunk in response.iter_content(1024 * 1024):
                    f.write(chunk)
                    written += len(chunk)
                    if written // (100 * 1024 * 1024) > milestone:
                        milestone = written // (100 * 1024 * 1024)
                        print(name, written // (1024 * 1024), "MiB", flush=True)
        if name == "pytorch_model.bin" and sha(part) != WEIGHT_SHA256:
            raise ValueError("Model checksum mismatch; snapshot was not published")
        os.replace(part, target)
    (root / "cineweave-model.json").write_text(json.dumps({"model": "BAAI/bge-m3", "revision": REVISION,
        "weight_sha256": WEIGHT_SHA256}, indent=2), encoding="utf-8")
    print("Pinned model ready:", str(root.resolve()), flush=True)


if __name__ == "__main__":
    main()
