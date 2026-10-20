import json

import numpy as np
import pytest

from semantic_service.app.index import SemanticIndex, digest
from semantic_service.offline.prepare_documents import clean, number


def make_index(root, vectors=None):
    folder = root / "v1"
    folder.mkdir()
    np.save(folder / "movie_ids.npy", np.array([9, 3, 7]))
    np.save(folder / "embeddings.npy", vectors if vectors is not None else np.array([[1., 0.], [0., 1.], [.6, .8]], dtype=np.float32))
    manifest = {"dimension": 2, "version": "v1", "files": {name: digest(folder / name) for name in ["movie_ids.npy", "embeddings.npy"]}}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "active.json").write_text(json.dumps({"version": "v1"}), encoding="utf-8")
    return folder


def test_exact_retrieval_respects_eligible_ids(tmp_path):
    make_index(tmp_path)
    index = SemanticIndex(tmp_path)
    items, scores = index.search(np.array([1., 0.]), [3, 7, 1000], 10)
    assert [c["movie_id"] for c in items] == [7, 3]
    assert set(scores) == {"3", "7"}


def test_empty_filter_does_not_fall_back_to_entire_catalog(tmp_path):
    make_index(tmp_path)
    assert SemanticIndex(tmp_path).search(np.array([1., 0.]), [], 10) == ([], {})


def test_tampered_file_fails_readiness(tmp_path):
    folder = make_index(tmp_path)
    (folder / "movie_ids.npy").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        SemanticIndex(tmp_path)


@pytest.mark.parametrize("vectors", [np.zeros((3, 2)), np.full((3, 2), np.nan), np.ones((2, 2))])
def test_invalid_vectors_rejected(tmp_path, vectors):
    make_index(tmp_path, vectors)
    with pytest.raises(ValueError):
        SemanticIndex(tmp_path)


def test_version_path_cannot_escape_root(tmp_path):
    (tmp_path / "active.json").write_text(json.dumps({"version": "../outside"}), encoding="utf-8")
    with pytest.raises(ValueError, match="path"):
        SemanticIndex(tmp_path)


@pytest.mark.parametrize("value,expected", [(None, ""), (float('nan'), ""), ("\\N", ""),
    ("Max&apos;s  story", "Max's story"), (" a\n b ", "a b")])
def test_content_cleaning(value, expected):
    assert clean(value) == expected


@pytest.mark.parametrize("value,expected", [("104", 104), ("\\N", None), (None, None), (float('nan'), None)])
def test_numbers(value, expected):
    assert number(value) == expected


def test_failed_build_does_not_replace_serving_pointer(tmp_path, monkeypatch):
    from semantic_service.offline import build_index
    make_index(tmp_path)
    before = (tmp_path / 'active.json').read_bytes()
    docs = [{'movie_id':i, 'title_type':'movie', 'description':'story', 'aliases':[],
             'runtime_minutes':100, 'source_title':'title', 'text':'a story'} for i in range(3)]
    class InvalidEncoder:
        def __init__(self, *args): pass
        def encode(self, texts, batch_size): return np.zeros((len(texts), 2), dtype=np.float32)
    monkeypatch.setattr(build_index, 'prepare', lambda path: docs)
    monkeypatch.setattr(build_index, 'Encoder', InvalidEncoder)
    with pytest.raises(ValueError, match='validation'):
        build_index.build(tmp_path, tmp_path, 'test-encoder', 'test-revision')
    assert (tmp_path / 'active.json').read_bytes() == before
    assert SemanticIndex(tmp_path).manifest['version'] == 'v1'


def test_valid_build_publishes_and_preserves_previous_pointer(tmp_path, monkeypatch):
    from semantic_service.offline import build_index
    make_index(tmp_path)
    docs = [{'movie_id':i, 'title_type':'movie', 'description':'story', 'aliases':[],
             'runtime_minutes':100, 'source_title':'title', 'text':'a story'} for i in range(3)]
    class ValidEncoder:
        def __init__(self, *args): pass
        def encode(self, texts, batch_size):
            return np.array([[1., 0.], [0., 1.], [.6, .8]], dtype=np.float32)
    monkeypatch.setattr(build_index, 'prepare', lambda path: docs)
    monkeypatch.setattr(build_index, 'Encoder', ValidEncoder)
    build_index.build(tmp_path, tmp_path, 'test-encoder', 'test-revision')
    assert SemanticIndex(tmp_path).manifest['version'] != 'v1'
    assert json.loads((tmp_path/'previous.json').read_text())['version'] == 'v1'
