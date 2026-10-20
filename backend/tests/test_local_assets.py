import hashlib
import json
import zipfile

import pytest

from scripts.configure_local import configure
from scripts.install_local_assets import checked_members, install


def archive_fixture(path, corrupt=False):
    payloads = {"data/movies.pkl": b"opaque trusted snapshot bytes",
                "models/model.txt": b"saved model placeholder for installer test only",
                "semantic_index/active.json": b'{"version":"test-v1"}'}
    manifest = {"format": "cineweave-local-assets-v1", "semantic_index_version": "test-v1",
                "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                          for name, data in payloads.items()}}
    with zipfile.ZipFile(path, "w") as z:
        for name, data in payloads.items():
            z.writestr(name, data + b"changed" if corrupt and name == "data/movies.pkl" else data)
        z.writestr("asset-manifest.json", json.dumps(manifest))


def test_restore_validated_assets_to_expected_paths(tmp_path):
    archive = tmp_path / "input.zip"
    archive_fixture(archive)
    root = tmp_path / "project"
    install(archive, root)
    assert (root / "artifacts/data/movies.pkl").read_bytes() == b"opaque trusted snapshot bytes"
    assert (root / "artifacts/processed/web_project/deployed_models/model.txt").is_file()
    assert json.loads((root / "artifacts/semantic_index/active.json").read_text())["version"] == "test-v1"


def test_restore_does_not_overwrite_current_data(tmp_path):
    archive = tmp_path / "input.zip"
    archive_fixture(archive)
    root = tmp_path / "project"
    target = root / "artifacts/data/movies.pkl"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        install(archive, root)
    assert target.read_bytes() == b"existing"
    assert not (root / "artifacts/semantic_index").exists()


def test_corruption_stops_install_before_writing(tmp_path):
    archive = tmp_path / "input.zip"
    archive_fixture(archive, corrupt=True)
    root = tmp_path / "project"
    with pytest.raises(ValueError, match="checksum mismatch"):
        install(archive, root)
    assert not root.exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "data/../../escape", "data/C:drive"])
def test_unsafe_archive_paths_are_rejected(tmp_path, name):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, b"bad")
    with zipfile.ZipFile(archive) as z, pytest.raises(ValueError, match="Unsafe"):
        checked_members(z)


def test_verify_only_never_creates_target(tmp_path):
    archive = tmp_path / "input.zip"
    archive_fixture(archive)
    root = tmp_path / "project"
    install(archive, root, verify_only=True)
    assert not root.exists()


def test_configure_preserves_existing_secrets(tmp_path):
    (tmp_path / ".env.example").write_text("DB_PASSWORD=replace\nSECRET_KEY=replace\n")
    env = tmp_path / ".env"
    configure(tmp_path, env)
    original = env.read_bytes()
    assert b"=replace" not in original
    with pytest.raises(FileExistsError):
        configure(tmp_path, env)
    assert env.read_bytes() == original
