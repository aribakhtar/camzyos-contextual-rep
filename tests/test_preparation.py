from pathlib import Path
from types import SimpleNamespace

import pytest

from camzyos import engine, graph, ingest, retrieval


@pytest.mark.parametrize("index_state,dimension,has_vector,ready", [
    ("ONLINE", 1536, True, True), ("POPULATING", 1536, True, False),
    ("ONLINE", 1024, True, False), ("ONLINE", 1536, False, False),
])
def test_index_readiness_checks_every_chunk_and_configuration(cfg, store, monkeypatch,
                                                             index_state, dimension, has_vector, ready):
    class Driver:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute_query(self, query, **kwargs):
            if query.startswith("SHOW"):
                return SimpleNamespace(records=[{"state": index_state,
                    "options": {"indexConfig": {"vector.dimensions": dimension}}}])
            assert kwargs["model"] == cfg["embedding_model"]
            assert kwargs["dimensions"] == cfg["embedding_dimensions"]
            return SimpleNamespace(records=[store.chunks()[0]] if has_vector else [])
    monkeypatch.setattr(graph, "driver", lambda cfg: Driver())
    assert graph.index_status(cfg, store.chunks())["ready"] is ready


def test_unready_index_blocks_model_before_generation(cfg, store, tables, monkeypatch):
    cfg["api_key"] = "test-placeholder"
    monkeypatch.setattr(graph, "index_status", lambda *a: {
        "ready": False, "indexed_chunks": 0, "eligible_chunks": 1, "index_state": "missing"})
    monkeypatch.setattr(engine, "parse", lambda *a: pytest.fail("No model calls before index readiness"))
    result = engine.ask(cfg, store, tables, "a@example.test", "General monitoring information")
    assert result["decision"] == "setup"
    assert "index is not ready" in result["answer"]
    assert result["citations"] == []


def test_vector_failure_does_not_silently_use_bm25(cfg, store, monkeypatch, indexed):
    def unavailable(*args):
        raise ConnectionError("Test outage")
    monkeypatch.setattr(graph, "vector_search", unavailable)
    with pytest.raises(retrieval.RetrievalNotReady, match="Vector retrieval is unavailable"):
        retrieval.retrieve(cfg, store, "monitoring")


@pytest.mark.parametrize("fails", [True, False])
def test_replacement_is_indexed_completely_before_atomic_activation(cfg, store, source, monkeypatch, fails):
    store.stage(source, "v2", "hash2", [{"text": "New monitoring passage.", "page": 2}], [], Path("new.pdf"))
    def index(cfg, chunks):
        assert {c["version_id"] for c in store.chunks()} == {"v1"}
        assert {c["version_id"] for c in chunks} == {"v2"}
        if fails:
            raise ConnectionError("Test interrupted embedding job")
    monkeypatch.setattr(graph, "index_chunks", index)
    if fails:
        with pytest.raises(ConnectionError):
            ingest.publish_version(cfg, store, "v2", "Reviewed fixture")
    else:
        ingest.publish_version(cfg, store, "v2", "Reviewed fixture")
    assert {c["version_id"] for c in store.chunks()} == ({"v1"} if fails else {"v2"})


def test_upload_pipeline_indexes_staged_version_without_activating(cfg, store, source, monkeypatch):
    def process(*args):
        store.stage(source, "v2", "hash2", [{"text": "New passage.", "page": 2}], [], Path("new.pdf"))
        return {"version": "v2", "status": "staged"}
    monkeypatch.setattr(ingest, "process", process)
    seen = []
    monkeypatch.setattr(graph, "index_chunks", lambda cfg, chunks: seen.extend(chunks) or len(chunks))
    result = ingest.process_document(cfg, store, source, Path("new.pdf"))
    assert result["indexed_chunks"] == 1
    assert seen[0]["version_id"] == "v2"
    assert {c["version_id"] for c in store.chunks()} == {"v1"}


def test_ineligible_source_cannot_be_indexed_from_staging(store, source):
    store.register([{**source, "market": "US"}])
    assert store.version_chunks("v1") == []


def test_dimension_mismatch_never_overwrites_existing_embeddings(cfg, store, monkeypatch):
    cfg["api_key"] = "test-placeholder"
    monkeypatch.setattr(graph, "index_status", lambda *a: {"index_state": "incompatible dimensions"})
    monkeypatch.setattr(graph, "driver", lambda *a: pytest.fail("No database writes before dimension check"))
    with pytest.raises(ValueError, match="dimensions differ"):
        graph.index_chunks(cfg, store.chunks())


def test_missing_explicit_upload_path_cannot_silently_use_cached_pdf(cfg, store, source, tmp_path):
    source["file"] = "cached.pdf"
    folder = cfg["data_dir"] / "public"
    folder.mkdir()
    (folder / source["file"]).write_bytes(b"%PDF-cached")
    with pytest.raises(FileNotFoundError, match="supplied PDF path"):
        ingest.process_document(cfg, store, source, tmp_path / "misspelled.pdf")
