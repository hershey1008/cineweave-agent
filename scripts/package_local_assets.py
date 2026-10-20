"""Package an existing trusted FunRec snapshot for LOCAL use; never uploads data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CORE = ("movies.pkl", "users.pkl", "ratings.pkl", "movie_metadata.pkl")
INDEX_FILES = ("documents.jsonl", "movie_ids.npy", "embeddings.npy", "quality_report.json", "manifest.json")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def collect(data_dir, models_dir, index_root, include_posters=True):
    entries = []
    for name in CORE:
        entries.append((data_dir / name, "data/" + name))
    required_models = ["vocab_dict.pkl", "item_embeddings.npy", "movie_ids.npy",
                       "ranking/vocab_dict.pkl", "ranking/feature_dict.pkl",
                       "model/user_recall/active.json", "model/ranking/active.json"]
    for name in required_models:
        if not (models_dir / name).is_file():
            raise FileNotFoundError(f"Missing model artifact: {name}")
    for name in ("user_recall", "ranking"):
        pointer = json.loads((models_dir / "model" / name / "active.json").read_text(encoding="utf-8"))
        target = (models_dir / pointer["path"]).resolve()
        if not target.is_relative_to(models_dir.resolve()) or not (target / "saved_model.pb").is_file():
            raise ValueError(f"Invalid or missing SavedModel: {name}")
    for path in sorted(models_dir.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            entries.append((path, "models/" + path.relative_to(models_dir).as_posix()))
    if include_posters:
        for path in sorted((data_dir / "image").glob("*")):
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                entries.append((path, "data/image/" + path.name))
    version = json.loads((index_root / "active.json").read_text(encoding="utf-8"))["version"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", version):
        raise ValueError("Invalid index version")
    entries.append((index_root / "active.json", "semantic_index/active.json"))
    for name in INDEX_FILES:
        entries.append((index_root / version / name, f"semantic_index/{version}/{name}"))
    for path, name in entries:
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"Missing or symlinked asset: {name}")
    return entries, version


def package(data_dir, models_dir, index_root, output, include_posters=True):
    entries, version = collect(data_dir, models_dir, index_root, include_posters)
    if output.exists():
        raise FileExistsError("Output already exists; choose a new filename")
    manifest = {"format": "cineweave-local-assets-v1", "public_redistribution": False,
        "source": "Existing locally processed FunRec / MovieLens-1M snapshot",
        "semantic_index_version": version, "posters_included": include_posters,
        "embedding_weights_included": False,
        "files": {name: {"bytes": path.stat().st_size, "sha256": digest(path)} for path, name in entries}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as zipped:
        for index, (path, name) in enumerate(entries, 1):
            zipped.write(path, name)
            if index % 500 == 0:
                print(f"Packaged {index}/{len(entries)} files", flush=True)
        zipped.writestr("asset-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    # Sidecar enables checking the archive before opening any pickle file.
    output.with_suffix(".zip.sha256").write_text(digest(output) + "  " + output.name + "\n", encoding="utf-8")
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"archive": str(output), "files": len(entries), "bytes": output.stat().st_size,
                      "index_version": version, "uploaded": False}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--funrec-root", type=Path, required=True)
    parser.add_argument("--index-root", type=Path, default=ROOT / "artifacts/semantic_index")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/distribution/cineweave-local-assets.zip")
    parser.add_argument("--without-posters", action="store_true")
    args = parser.parse_args()
    package(args.funrec_root / "funrec-movielens-1m",
            args.funrec_root / "processed_data/web_project/deployed_models",
            args.index_root, args.output, not args.without_posters)
