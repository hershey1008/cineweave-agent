"""Verify and install a trusted local archive into empty application asset paths."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DESTINATIONS = {"data": "artifacts/data", "models": "artifacts/processed/web_project/deployed_models",
                "semantic_index": "artifacts/semantic_index"}


def checked_members(zipped):
    entries = zipped.infolist()
    names = [item.filename for item in entries]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate archive members")
    if any(item.file_size > 3 * 1024**3 for item in entries) or sum(item.file_size for item in entries) > 10 * 1024**3:
        raise ValueError("Unexpected archive size")
    for name in names:
        path = PurePosixPath(name)
        if "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe archive member")
        if name != "asset-manifest.json" and (not path.parts or path.parts[0] not in DESTINATIONS):
            raise ValueError("Unexpected archive member")
    manifest = json.loads(zipped.read("asset-manifest.json"))
    if manifest.get("format") != "cineweave-local-assets-v1":
        raise ValueError("Unsupported archive format")
    if set(names) != set(manifest["files"]) | {"asset-manifest.json"}:
        raise ValueError("Archive inventory mismatch")
    for name, record in manifest["files"].items():
        actual = hashlib.sha256()
        with zipped.open(name) as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                actual.update(block)
        if zipped.getinfo(name).file_size != record["bytes"] or actual.hexdigest() != record["sha256"]:
            raise ValueError(f"Asset checksum mismatch: {name}")
    return manifest


def install(archive, root=ROOT, verify_only=False):
    # Validation reads bytes only; this tool never unpickles supplied data.
    with zipfile.ZipFile(archive) as zipped:
        manifest = checked_members(zipped)
        if not verify_only:
            for target in DESTINATIONS.values():
                folder = root / target
                if folder.exists() and any(folder.iterdir()):
                    raise FileExistsError(f"Target is not empty: {target}; use a fresh checkout")
            (root / "artifacts").mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="asset-install-", dir=root / "artifacts") as staging:
                temporary = Path(staging)
                for name in manifest["files"]:
                    path = temporary / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with zipped.open(name) as source, path.open("wb") as target:
                        shutil.copyfileobj(source, target, length=4 * 1024 * 1024)
                for prefix, relative in DESTINATIONS.items():
                    destination = root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(temporary / prefix, destination, dirs_exist_ok=True)
    print(json.dumps({"verified": True, "installed": not verify_only,
                      "files": len(manifest["files"]), "index_version": manifest["semantic_index_version"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    install(args.archive, verify_only=args.verify_only)
