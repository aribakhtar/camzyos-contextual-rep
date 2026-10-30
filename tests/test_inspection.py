"""Offline inspection-corpus contracts; synthetic PDFs contain no clinical claims."""

import hashlib
import json
import socket
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pymupdf as fitz
import pytest
import yaml

from camzyos import cli, engine, graph, inspection, retrieval
from camzyos import settings as settings_module
from camzyos.store import Store

ROOT = Path(__file__).resolve().parents[1]
PAGE_TEXT = (
    "Amber archive contains a catalog of paper folders. "
    "The inventory records folder colors and shelf locations. "
    "These neutral sentences are only extraction fixtures.",
    "Tiny.",
    "Cobalt inventory table: blue folders, green folders, and spare labels.",
    "",
)


def forbidden(*args, **kwargs):
    pytest.fail("Inspection tests must not read .env, use live services, or call clinical writers/generation")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(settings_module, "load_dotenv", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(graph, "driver", forbidden)
    monkeypatch.setattr(graph, "index_chunks", forbidden)
    monkeypatch.setattr(engine, "parse", forbidden)
    monkeypatch.setattr(inspection, "OpenAI", forbidden)


@pytest.fixture
def cfg(tmp_path):
    """Override conftest.cfg: settings() would read the developer's .env."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    return {
        "data_dir": tmp_path / "data", "pdf_dir": pdf_dir,
        "chunk_target_chars": 1600, "chunk_overlap_sentences": 1,
        "retrieval_top_k": 6, "embedding_model": "offline-embedding-fixture",
        "embedding_dimensions": 4, "api_key": "", "base_url": "https://api.example.invalid/v1",
        "neo4j_uri": "bolt://example.invalid:7687", "neo4j_user": "offline",
        "neo4j_password": "", "neo4j_database": "offline", "graphiti_enabled": False,
    }


def write_pdf(path, texts=PAGE_TEXT, drawings=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as pdf:
        for number, text in enumerate(texts, 1):
            page = pdf.new_page()
            if text:
                assert page.insert_textbox(fitz.Rect(40, 100, 550, 700), text, fontsize=11) >= 0
            if drawings and number == 3:
                for index in range(30):
                    x = 40 + index * 12
                    page.draw_rect(fitz.Rect(x, 300, x + 8, 310))
        pdf.save(path)
    return path


@pytest.fixture
def inspection_source(cfg):
    source = {
        "id": "archive", "file": "archive.pdf", "title": "Neutral archive fixture",
        "market": "DE", "audience": "HCP", "eligible": True, "language": "en",
        "kind": "inventory", "pages": [1, 1], "review_pages": [3],
    }
    write_pdf(cfg["pdf_dir"] / source["file"])
    return source


@pytest.fixture
def catalog(cfg, inspection_source):
    us = {**inspection_source, "id": "us_archive", "file": "us.pdf", "market": "US", "eligible": False}
    public = {**inspection_source, "id": "public_archive", "file": "public.pdf",
              "audience": "public", "eligible": False}
    write_pdf(cfg["pdf_dir"] / us["file"])
    write_pdf(cfg["data_dir"] / "public" / public["file"])
    return [inspection_source, us, public]


@pytest.fixture
def account_catalog(cfg, inspection_source):
    public = {**inspection_source, "audience": "public", "eligible": False}
    private_a = {**inspection_source, "id": "archive_a", "file": "a.pdf", "account_id": "account_A"}
    private_b = {**inspection_source, "id": "archive_b", "file": "b.pdf", "account_id": "account_B"}
    for source, text in ((public, "Public linen inventory."),
                         (private_a, "Amberprivate folder inventory."),
                         (private_b, "Blueprivate folder inventory.")):
        write_pdf(cfg["pdf_dir"] / source["file"], [text])
    return [public, private_a, private_b]


def readiness(chunks, missing=(), state="ONLINE"):
    missing = set(missing)
    return {
        "ready": bool(chunks) and state == "ONLINE" and not missing,
        "index_name": "camzyos_inspection_embeddings", "index_state": state,
        "expected_chunks": len(chunks), "indexed_chunks": len(chunks) - len(missing),
        "missing_ids": sorted(missing),
    }


@pytest.fixture
def fake_index(monkeypatch):
    indexed = {}

    def status(cfg, chunks):
        missing = [c["id"] for c in chunks if indexed.get(c["id"]) != c["text"]]
        return readiness(chunks, missing)

    def index(cfg, chunks):
        pending = status(cfg, chunks)["missing_ids"]
        indexed.update({c["id"]: c["text"] for c in chunks})
        return {**status(cfg, chunks), "new_embeddings": len(pending)}

    monkeypatch.setattr(inspection, "index_chunks", index)
    monkeypatch.setattr(inspection, "index_status", status)
    return indexed


def manifest_path(cfg):
    return cfg["data_dir"] / "inspection" / "manifest.json"


def version_files(cfg):
    return sorted((cfg["data_dir"] / "inspection" / "versions").glob("*.json"))


def assert_page_coverage(document, path):
    """Compare against PyMuPDF directly, including every non-whitespace character."""
    with fitz.open(path) as pdf:
        assert [p["page"] for p in document["pages"]] == list(range(1, len(pdf) + 1))
        for number, raw_page in enumerate(pdf, 1):
            text = raw_page.get_text("text", flags=fitz.TEXT_DEHYPHENATE)
            assert document["pages"][number - 1]["text"] == text
            covered = set()
            for chunk in (c for c in document["chunks"] if c["page"] == number):
                start, end = chunk["char_start"], chunk["char_end"]
                assert 0 <= start < end <= len(text)
                assert chunk["page_end"] == number
                assert chunk["text"] == text[start:end]
                covered.update(range(start, end))
            assert {i for i, char in enumerate(text) if not char.isspace()} <= covered


def test_prepare_retains_all_text_pages_and_reports_blank_pages(cfg, inspection_source):
    document = inspection.prepare_source(cfg, inspection_source)

    assert document["source_id"] == inspection_source["id"]
    assert document["source"] == inspection_source
    assert document["file"] == inspection_source["file"]
    assert document["sha256"] == hashlib.sha256(
        (cfg["pdf_dir"] / inspection_source["file"]).read_bytes()).hexdigest()
    assert document["checksum"]
    assert document["page_count"] == 4
    assert document["pages_with_text"] == [1, 2, 3]
    assert document["no_text_pages"] == [4]
    assert document["review_pages"] == [3]
    chunks = document["chunks"]
    assert document["chunk_count"] == len(chunks) == 3
    assert len({c["id"] for c in chunks}) == len(chunks)
    for chunk, expected in zip(chunks, PAGE_TEXT):
        assert " ".join(chunk["text"].split()) == expected
        assert chunk["id"].startswith("inspection:")
        assert chunk["version_id"] == document["version_id"]
        assert chunk["source"] == inspection_source
        assert chunk["page_end"] == chunk["page"]
        assert chunk["section"]
        assert chunk["requires_review"] is (chunk["page"] == 3)
        assert chunk["corpus"] == "inspection"
        assert chunk["clinical_evidence"] is False
    assert {c["page"] for c in chunks} == {1, 2, 3}
    assert [a["page"] for a in document["audit"]] == [1, 2, 3, 4]
    assert [a["inspection_chunks"] for a in document["audit"]] == [1, 1, 1, 0]
    assert document["audit"][-1]["text_chars"] == 0
    assert_page_coverage(document, cfg["pdf_dir"] / inspection_source["file"])


def test_repeated_margins_and_footer_only_pages_are_kept_with_cleanup_audit(cfg, inspection_source):
    path = cfg["pdf_dir"] / inspection_source["file"]
    with fitz.open() as pdf:
        for number in range(1, 5):
            page = pdf.new_page()
            page.insert_text((40, 30), "Repeated archive banner")
            page.insert_text((40, 810), str(number))
        pdf.save(path)
    document = inspection.prepare_source(cfg, inspection_source)
    assert document["pages_with_text"] == [1, 2, 3, 4]
    assert document["no_text_pages"] == []
    assert all("Repeated archive banner" in chunk["text"] for chunk in document["chunks"])
    assert all("Repeated archive banner" in entry["removed_margin_lines"] for entry in document["audit"])
    assert all(entry["text_chars"] == 0 and entry["raw_text_chars"] > 0 for entry in document["audit"])
    assert_page_coverage(document, path)


@pytest.mark.parametrize("overlap", [0, 1, 2])
def test_chunk_spans_cover_all_text_across_small_chunk_boundaries(cfg, inspection_source, overlap):
    path = cfg["pdf_dir"] / inspection_source["file"]
    texts = [" ".join(f"Folder number {i} has an amber label." for i in range(12)), "x", PAGE_TEXT[2], ""]
    write_pdf(path, texts)
    cfg.update(chunk_target_chars=85, chunk_overlap_sentences=overlap)
    document = inspection.prepare_source(cfg, inspection_source)
    assert sum(c["page"] == 1 for c in document["chunks"]) > 1
    assert document["pages_with_text"] == [1, 2, 3]
    assert document["no_text_pages"] == [4]
    assert_page_coverage(document, path)


def test_automatically_detected_structured_page_is_retained(cfg, inspection_source):
    source = {**inspection_source, "review_pages": []}
    write_pdf(cfg["pdf_dir"] / source["file"], drawings=True)
    document = inspection.prepare_source(cfg, source)
    assert document["review_pages"] == [3]
    structured = [c for c in document["chunks"] if c["page"] == 3]
    assert structured and all(c["requires_review"] for c in structured)
    assert "Cobalt inventory" in structured[0]["text"]


def test_preparation_reuses_immutable_cache_without_reextracting(cfg, inspection_source, monkeypatch):
    first = inspection.prepare_source(cfg, inspection_source)
    artifacts = version_files(cfg)
    assert len(artifacts) == 1
    artifact = artifacts[0]
    before = artifact.read_bytes(), artifact.stat().st_mtime_ns
    assert json.loads(before[0]) == first
    monkeypatch.setattr(inspection, "extract", forbidden)
    assert inspection.prepare_source(cfg, inspection_source) == first
    assert (artifact.read_bytes(), artifact.stat().st_mtime_ns) == before
    assert version_files(cfg) == artifacts
    assert not manifest_path(cfg).exists()


def test_new_preparation_preserves_previous_version(cfg, inspection_source):
    first = inspection.prepare_source(cfg, inspection_source)
    original = version_files(cfg)[0]
    before = original.read_bytes()
    write_pdf(cfg["pdf_dir"] / inspection_source["file"], ["Revised neutral archive inventory."])
    second = inspection.prepare_source(cfg, inspection_source)
    assert second["sha256"] != first["sha256"]
    assert second["version_id"] != first["version_id"]
    assert second["checksum"] != first["checksum"]
    assert original.read_bytes() == before
    assert len(version_files(cfg)) == 2
    assert {c["id"] for c in first["chunks"]}.isdisjoint(c["id"] for c in second["chunks"])


def test_corrupted_cached_document_is_rejected(cfg, inspection_source):
    inspection.prepare_source(cfg, inspection_source)
    artifact = version_files(cfg)[0]
    document = json.loads(artifact.read_text(encoding="utf-8"))
    document["chunks"][0]["text"] = "Tampered inventory."
    artifact.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        inspection.prepare_source(cfg, inspection_source)


def test_explicit_path_is_used_and_missing_explicit_path_never_falls_back(cfg, inspection_source, tmp_path):
    supplied = write_pdf(tmp_path / "supplied.pdf", ["Explicit archive copy."])
    document = inspection.prepare_source(cfg, inspection_source, path=supplied)
    assert document["chunks"][0]["text"] == "Explicit archive copy."
    assert document["sha256"] == hashlib.sha256(supplied.read_bytes()).hexdigest()
    with pytest.raises(FileNotFoundError):
        inspection.prepare_source(cfg, inspection_source, path=tmp_path / "missing.pdf")


def test_build_indexes_entire_catalog_before_publishing(cfg, catalog, fake_index, monkeypatch):
    index = inspection.index_chunks
    batches = []

    def checking_index(config, chunks):
        assert not manifest_path(config).exists()
        assert len(version_files(config)) == len(catalog)
        batches.append(chunks)
        return index(config, chunks)

    monkeypatch.setattr(inspection, "index_chunks", checking_index)
    status = inspection.build(cfg, catalog)
    documents = inspection.load(cfg, catalog)
    assert len(batches) == 1
    assert {c["source"]["id"] for c in batches[0]} == {s["id"] for s in catalog}
    assert batches[0] == [c for d in documents for c in d["chunks"]]
    assert len(documents) == 3
    assert all(d["pages_with_text"] == [1, 2, 3] for d in documents)
    assert all(c["clinical_evidence"] is False for c in batches[0])
    assert status["ready"] is True
    assert status["expected_chunks"] == status["indexed_chunks"] == len(batches[0])
    assert status["missing_ids"] == []
    assert status["errors"] == []


def test_staged_source_is_inspectable_without_clinical_store_writes(
        cfg, inspection_source, fake_index, monkeypatch):
    clinical = Store(cfg["data_dir"])
    clinical.register([inspection_source])
    clinical.stage(inspection_source, "staged-fixture", "fixture-hash",
                   [{"text": "Staged neutral inventory.", "page": 1}], [],
                   cfg["pdf_dir"] / inspection_source["file"])
    assert clinical.versions()[0]["status"] == "staged"
    assert clinical.chunks() == []
    before = clinical.path.read_bytes()
    for method in ("__init__", "register", "stage", "activate", "deactivate", "remember", "delivered"):
        monkeypatch.setattr(Store, method, forbidden)
    inspection.build(cfg, [inspection_source])
    assert inspection.load(cfg, [inspection_source])[0]["chunks"]
    assert clinical.path.read_bytes() == before
    assert clinical.versions()[0]["status"] == "staged"
    assert clinical.chunks() == []


@pytest.mark.parametrize("change", ["bytes", "title", "eligible", "pages", "review_pages", "target", "overlap"])
def test_changed_inputs_invalidate_manifest(cfg, inspection_source, fake_index, change):
    catalog = [inspection_source]
    inspection.build(cfg, catalog)
    before = manifest_path(cfg).read_bytes()
    if change == "bytes":
        write_pdf(cfg["pdf_dir"] / inspection_source["file"], ["Changed folder inventory."])
    elif change == "target":
        cfg["chunk_target_chars"] += 50
    elif change == "overlap":
        cfg["chunk_overlap_sentences"] = 0
    else:
        updates = {"title": "Revised archive title", "eligible": False, "pages": [2, 3], "review_pages": [2, 3]}
        catalog = [{**inspection_source, change: updates[change]}]
    with pytest.raises(ValueError):
        inspection.load(cfg, catalog)
    status = inspection.report(cfg, catalog)
    assert status["ready"] is False
    assert status["errors"]
    assert manifest_path(cfg).read_bytes() == before


@pytest.mark.parametrize("damage", ["missing_manifest", "missing_pdf", "incomplete", "checksum"])
def test_load_rejects_missing_incomplete_or_tampered_corpus(cfg, catalog, fake_index, damage):
    inspection.build(cfg, catalog)
    path = manifest_path(cfg)
    if damage == "missing_manifest":
        path.unlink()
    elif damage == "missing_pdf":
        (cfg["pdf_dir"] / catalog[0]["file"]).unlink()
    else:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if damage == "incomplete":
            manifest["documents"].pop()
        else:
            manifest["documents"][0]["chunks"][0]["text"] = "Unrecorded archive edit."
        path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        inspection.load(cfg, catalog)
    status = inspection.report(cfg, catalog)
    assert status["ready"] is False
    assert status["errors"]


@pytest.mark.parametrize("damage", ["missing_page", "missing_chunk", "wrong_slice", "duplicate_id"])
def test_load_validates_coverage_even_with_recomputed_checksum(cfg, catalog, fake_index, damage):
    inspection.build(cfg, catalog)
    path = manifest_path(cfg)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    document = manifest["documents"][0]
    if damage == "missing_page":
        document["pages"].pop(1)
    elif damage == "missing_chunk":
        document["chunks"].pop(1)
        document["chunk_count"] -= 1
    elif damage == "wrong_slice":
        document["chunks"][0]["char_start"] += 1
    else:
        document["chunks"][1]["id"] = document["chunks"][0]["id"]
    payload = {key: value for key, value in document.items() if key != "checksum"}
    document["checksum"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="inventory|dropped|preserve|Duplicate"):
        inspection.load(cfg, catalog)


@pytest.mark.parametrize("existing_manifest", [False, True])
@pytest.mark.parametrize("failure", ["exception", "incomplete", "changed_during_indexing"])
def test_failed_build_cannot_publish_manifest(
        cfg, catalog, fake_index, monkeypatch, existing_manifest, failure):
    path = manifest_path(cfg)
    if existing_manifest:
        inspection.build(cfg, catalog)
    previous = path.read_bytes() if path.exists() else None
    # Give the attempted run a new immutable version, distinct from any published run.
    write_pdf(cfg["pdf_dir"] / catalog[0]["file"], ["Replacement neutral archive."])
    attempted = []

    def interrupted(config, chunks):
        assert (path.read_bytes() if path.exists() else None) == previous
        attempted.extend(chunks)
        if failure == "exception":
            fake_index[chunks[0]["id"]] = chunks[0]["text"]
            raise ConnectionError("Synthetic interruption after one passage")
        if failure == "incomplete":
            return {**readiness(chunks, [chunks[-1]["id"]]), "new_embeddings": len(chunks) - 1}
        write_pdf(config["pdf_dir"] / catalog[0]["file"], ["Archive changed during embedding."])
        return {**readiness(chunks), "new_embeddings": len(chunks)}

    monkeypatch.setattr(inspection, "index_chunks", interrupted)
    with pytest.raises((ConnectionError, RuntimeError)):
        inspection.build(cfg, catalog)
    assert {c["source"]["id"] for c in attempted} == {s["id"] for s in catalog}
    assert (path.read_bytes() if path.exists() else None) == previous


def test_missing_source_aborts_build_before_indexing(cfg, catalog, monkeypatch):
    (cfg["pdf_dir"] / catalog[1]["file"]).unlink()
    monkeypatch.setattr(inspection, "index_chunks", forbidden)
    with pytest.raises(FileNotFoundError):
        inspection.build(cfg, catalog)
    assert not manifest_path(cfg).exists()


def test_build_raises_when_final_report_loses_readiness(cfg, catalog, fake_index, monkeypatch):
    index = inspection.index_chunks
    indexed_results = []
    lost_ids = []

    def index_then_lose_passage(config, chunks):
        result = index(config, chunks)
        assert result["ready"] is True
        indexed_results.append(result)
        lost_ids.append(chunks[-1]["id"])
        del fake_index[lost_ids[-1]]
        return result

    monkeypatch.setattr(inspection, "index_chunks", index_then_lose_passage)
    with pytest.raises(RuntimeError, match="readiness changed after indexing"):
        inspection.build(cfg, catalog)
    assert len(indexed_results) == 1
    status = inspection.report(cfg, catalog)
    assert status["ready"] is False
    assert status["missing_ids"] == lost_ids
    assert status["indexed_chunks"] == indexed_results[0]["indexed_chunks"] - 1


def test_report_is_read_only_and_accounts_for_each_source(cfg, catalog, fake_index, monkeypatch):
    inspection.build(cfg, catalog)
    documents = inspection.load(cfg, catalog)
    missing = documents[-1]["chunks"][-1]["id"]
    del fake_index[missing]
    before = manifest_path(cfg).read_bytes()
    monkeypatch.setattr(inspection, "index_chunks", forbidden)
    monkeypatch.setattr(inspection, "_vector_search", forbidden)
    monkeypatch.setattr(inspection, "prepare_source", forbidden)
    status = inspection.report(cfg, catalog)
    total = sum(d["chunk_count"] for d in documents)
    assert status["ready"] is False
    assert status["index_state"] == "ONLINE"
    assert status["expected_chunks"] == total
    assert status["indexed_chunks"] == total - 1
    assert status["missing_ids"] == [missing]
    assert status["errors"] == []
    rows = {row["source_id"]: row for row in status["documents"]}
    assert set(rows) == {s["id"] for s in catalog}
    for document in documents:
        row = rows[document["source_id"]]
        assert row["chunk_count"] == document["chunk_count"]
        assert row["page_count"] == 4
        assert row["text_pages_expected"] == 3
        assert row["text_pages_indexed"] == 3 - (document is documents[-1])
        assert row["no_text_pages"] == [4]
        assert row["review_pages"] == [3]
        assert row["clinical_evidence"] is False
        assert row["indexed_chunks"] == document["chunk_count"] - (document is documents[-1])
    assert manifest_path(cfg).read_bytes() == before


@pytest.mark.parametrize("condition", ["ready", "uppercase_cosine", "missing", "partial", "stale_text", "populating",
                                      "dimensions", "similarity", "label", "property", "unavailable",
                                      "version_id", "source_id", "page"])
def test_index_status_checks_separate_index_and_every_passage(cfg, inspection_source, monkeypatch, condition):
    chunks = inspection.prepare_source(cfg, inspection_source)["chunks"]
    calls = []

    def execute(query, **kwargs):
        calls.append(query)
        assert kwargs["database_"] == cfg["neo4j_database"]
        assert "CamzyosChunk" not in query and "camzyos_embeddings" not in query
        if condition == "unavailable":
            raise ConnectionError("Synthetic database outage")
        if query.startswith("SHOW"):
            assert kwargs["index"] == "camzyos_inspection_embeddings"
            if condition == "missing":
                return SimpleNamespace(records=[])
            return SimpleNamespace(records=[{
                "state": "POPULATING" if condition == "populating" else "ONLINE",
                "labelsOrTypes": ["CamzyosChunk" if condition == "label" else "CamzyosInspectionChunk"],
                "properties": ["wrong_embedding" if condition == "property" else "embedding"],
                "options": {"indexConfig": {
                    "vector.dimensions": 99 if condition == "dimensions" else cfg["embedding_dimensions"],
                    "vector.similarity_function": ("euclidean" if condition == "similarity"
                                                   else "COSINE" if condition == "uppercase_cosine" else "cosine"),
                }},
            }])
        assert query.startswith("MATCH") and "CamzyosInspectionChunk" in query
        assert "c.corpus='inspection'" in query and "c.clinical_evidence=false" in query
        assert kwargs["model"] == cfg["embedding_model"]
        assert kwargs["dimensions"] == cfg["embedding_dimensions"]
        assert set(kwargs["ids"]) == {c["id"] for c in chunks}
        rows = [{"id": c["id"], "text": c["text"], "version_id": c["version_id"],
                 "source_id": c["source"]["id"], "page": c["page"]} for c in chunks]
        if condition == "partial":
            rows.pop()
        elif condition == "stale_text":
            rows[-1]["text"] = "Outdated folder inventory."
        elif condition in {"version_id", "source_id", "page"}:
            rows[-1][condition] = 99 if condition == "page" else "outdated"
        return SimpleNamespace(records=rows)

    monkeypatch.setattr(graph, "driver", lambda cfg: nullcontext(SimpleNamespace(execute_query=execute)))
    status = inspection.index_status(cfg, chunks)
    assert calls
    assert status["index_name"] == "camzyos_inspection_embeddings"
    assert status["expected_chunks"] == len(chunks)
    assert status["ready"] is (condition in {"ready", "uppercase_cosine"})
    if condition in {"ready", "uppercase_cosine", "populating"}:
        assert status["indexed_chunks"] == len(chunks)
        assert status["missing_ids"] == []
    elif condition in {"partial", "stale_text", "version_id", "source_id", "page"}:
        assert status["indexed_chunks"] == len(chunks) - 1
        assert status["missing_ids"] == [chunks[-1]["id"]]
    else:
        assert status["indexed_chunks"] == 0
        assert set(status["missing_ids"]) == {c["id"] for c in chunks}


def test_index_writes_only_inspection_nodes_and_reuses_embeddings(cfg, inspection_source, monkeypatch):
    chunks = inspection.prepare_source(cfg, inspection_source)["chunks"]
    cfg["api_key"] = "offline-placeholder"
    rows, queries, embedded = {}, [], []

    def execute(query, **kwargs):
        queries.append(query)
        assert "CamzyosChunk" not in query and "camzyos_embeddings" not in query
        if query.startswith("SHOW"):
            assert kwargs["index"] == "camzyos_inspection_embeddings"
            return SimpleNamespace(records=[{
                "state": "ONLINE", "labelsOrTypes": ["CamzyosInspectionChunk"], "properties": ["embedding"],
                "options": {"indexConfig": {"vector.dimensions": cfg["embedding_dimensions"],
                                            "vector.similarity_function": "cosine"}},
            }])
        if query.startswith("MATCH"):
            assert "CamzyosInspectionChunk" in query
            return SimpleNamespace(records=list(rows.values()))
        if query.startswith("CREATE"):
            assert "CamzyosInspectionChunk" in query
        elif query.startswith("UNWIND"):
            assert "MERGE(c:CamzyosInspectionChunk" in query
            assert "c.corpus='inspection'" in query and "c.clinical_evidence=false" in query
            rows.update({row["id"]: row for row in kwargs["rows"]})
        elif query.startswith("CALL"):
            assert kwargs["index"] == "camzyos_inspection_embeddings"
        else:
            pytest.fail(f"Unexpected database operation: {query}")
        return SimpleNamespace(records=[])

    def embed(**kwargs):
        assert kwargs["model"] == cfg["embedding_model"]
        assert kwargs["dimensions"] == cfg["embedding_dimensions"]
        embedded.extend(kwargs["input"])
        return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=[float(i + 1)] * 4)
                                     for i in reversed(range(len(kwargs["input"])))])

    monkeypatch.setattr(graph, "driver", lambda cfg: nullcontext(SimpleNamespace(execute_query=execute)))
    monkeypatch.setattr(inspection, "OpenAI", lambda **kwargs: nullcontext(
        SimpleNamespace(embeddings=SimpleNamespace(create=embed))))
    first = inspection.index_chunks(cfg, chunks)
    writes = sum(q.startswith(("CREATE", "UNWIND")) for q in queries)
    assert writes > 0
    assert first["ready"] is True
    assert first["new_embeddings"] == len(chunks)
    assert embedded == [c["text"] for c in chunks]
    assert set(rows) == {c["id"] for c in chunks}
    for index, chunk in enumerate(chunks):
        assert rows[chunk["id"]]["embedding"] == [float(index + 1)] * 4
        assert rows[chunk["id"]]["source_id"] == inspection_source["id"]
        assert rows[chunk["id"]]["version_id"] == chunk["version_id"]
    second = inspection.index_chunks(cfg, chunks)
    assert second["ready"] is True and second["new_embeddings"] == 0
    assert embedded == [c["text"] for c in chunks]
    assert sum(q.startswith(("CREATE", "UNWIND")) for q in queries) == writes


@pytest.mark.parametrize("damage", ["missing_item", "duplicate_index", "extra_item", "wrong_index",
                                   "short_vector", "long_vector", "nan", "infinity", "negative_infinity"])
def test_malformed_embedding_response_never_writes_passages(cfg, inspection_source, monkeypatch, damage):
    cfg["api_key"] = "offline-placeholder"
    chunks = inspection.prepare_source(cfg, inspection_source)["chunks"]
    calls = []
    monkeypatch.setattr(inspection, "index_status", lambda cfg, chunks: readiness(
        chunks, [c["id"] for c in chunks], "missing"))

    def execute(query, **kwargs):
        # Schema creation is allowed; no passage from a malformed batch may be written.
        assert query.startswith("CREATE") and "CamzyosInspectionChunk" in query
        return SimpleNamespace(records=[])

    def embed(**kwargs):
        calls.append(kwargs)
        data = [SimpleNamespace(index=i, embedding=[0.25] * 4) for i in range(len(chunks))]
        if damage == "missing_item":
            data.pop()
        elif damage == "duplicate_index":
            data[-1].index = 0
        elif damage == "extra_item":
            data.append(SimpleNamespace(index=len(chunks), embedding=[0.25] * 4))
        elif damage == "wrong_index":
            data[-1].index = len(chunks) + 1
        elif damage == "short_vector":
            data[-1].embedding.pop()
        elif damage == "long_vector":
            data[-1].embedding.append(0.25)
        else:
            data[-1].embedding[-1] = {"nan": float("nan"), "infinity": float("inf"),
                                     "negative_infinity": -float("inf")}[damage]
        return SimpleNamespace(data=data)

    monkeypatch.setattr(graph, "driver", lambda cfg: nullcontext(SimpleNamespace(execute_query=execute)))
    monkeypatch.setattr(inspection, "OpenAI", lambda **kwargs: nullcontext(
        SimpleNamespace(embeddings=SimpleNamespace(create=embed))))
    with pytest.raises(ValueError, match="batch|dimensions or values"):
        inspection.index_chunks(cfg, chunks)
    assert len(calls) == 1
    assert calls[0]["input"] == [c["text"] for c in chunks]


@pytest.mark.parametrize("changes", [{"corpus": "clinical"}, {"clinical_evidence": True}, {"id": "v1:0"}])
def test_inspection_index_refuses_clinical_passages(cfg, inspection_source, changes):
    cfg["api_key"] = "offline-placeholder"
    chunk = inspection.prepare_source(cfg, inspection_source)["chunks"][0]
    with pytest.raises(ValueError, match="inspection"):
        inspection.index_chunks(cfg, [{**chunk, **changes}])


@pytest.mark.parametrize("state", ["missing", "POPULATING", "ONLINE"])
def test_search_refuses_missing_or_incomplete_index_before_vector_search(
        cfg, catalog, fake_index, monkeypatch, state):
    inspection.build(cfg, catalog)
    documents = inspection.load(cfg, catalog)
    missing = documents[-1]["chunks"][-1]["id"]
    monkeypatch.setattr(inspection, "index_status", lambda cfg, chunks: readiness(chunks, [missing], state))
    monkeypatch.setattr(inspection, "_vector_search", forbidden)
    with pytest.raises(RuntimeError, match="index is not ready"):
        inspection.search(cfg, catalog, "Amber archive", source_id=catalog[0]["id"])


def test_inspection_search_filters_sources_and_never_generates(cfg, catalog, fake_index, monkeypatch):
    inspection.build(cfg, catalog)
    documents = inspection.load(cfg, catalog)
    chosen = documents[1]
    allowed = {c["id"] for c in chosen["chunks"]}

    def vector(config, question, chunks):
        assert {c["id"] for c in chunks} == allowed
        return [documents[0]["chunks"][0]["id"], "clinical:v1:0", *reversed(sorted(allowed))]

    monkeypatch.setattr(inspection, "_vector_search", vector)
    result = inspection.search(cfg, catalog, "Cobalt inventory", source_id=chosen["source_id"])
    assert result["decision"] == "inspection"
    assert result["clinical_evidence"] is False
    assert result["answer_generated"] is False
    assert result["corpus_revision"]
    assert {c["id"] for c in result["retrieved_passages"]} == allowed
    assert all(c["corpus"] == "inspection" and c["clinical_evidence"] is False
               for c in result["retrieved_passages"])
    assert any(c["requires_review"] for c in result["retrieved_passages"])
    again = inspection.search(cfg, catalog, "Tiny", source_id=chosen["source_id"])
    assert again["corpus_revision"] == result["corpus_revision"]


def test_administrative_build_load_and_report_include_all_accounts(cfg, account_catalog, fake_index):
    status = inspection.build(cfg, account_catalog)
    documents = inspection.load(cfg, account_catalog)
    assert {d["source_id"] for d in documents} == {s["id"] for s in account_catalog}
    assert {d["source"].get("account_id") for d in documents} == {None, "account_A", "account_B"}
    assert set(fake_index) == {c["id"] for d in documents for c in d["chunks"]}
    assert status["ready"] is True
    assert status["expected_chunks"] == status["indexed_chunks"] == 3
    assert {d["source_id"] for d in status["documents"]} == {s["id"] for s in account_catalog}


@pytest.mark.parametrize("account_id,source_id,expected_sources", [
    (None, None, {"archive"}),
    ("", None, {"archive"}),
    ("unknown", None, {"archive"}),
    ("account_B", None, {"archive", "archive_b"}),
    ("account_A", None, {"archive", "archive_a"}),
    ("account_A", "archive_a", {"archive_a"}),
])
def test_search_scopes_both_rankers_and_rejects_injected_private_ids(
        cfg, account_catalog, fake_index, monkeypatch, account_id, source_id, expected_sources):
    inspection.build(cfg, account_catalog)
    documents = inspection.load(cfg, account_catalog)
    chunks = [c for d in documents for c in d["chunks"]]
    expected = [c for d in documents if d["source_id"] in expected_sources for c in d["chunks"]]
    allowed_ids = {c["id"] for c in expected}
    excluded = [c for c in chunks if c["id"] not in allowed_ids]
    bm25 = inspection.BM25Plus
    seen = []

    def vector(config, question, candidates):
        seen.append("vector")
        assert {c["id"] for c in candidates} == allowed_ids
        # Simulate a backend returning forbidden passages ahead of permitted ones.
        return [c["id"] for c in excluded] + [c["id"] for c in expected]

    def lexical(corpus):
        seen.append("lexical")
        assert corpus == [retrieval.tokens(c["text"]) for c in expected]
        return bm25(corpus)

    monkeypatch.setattr(inspection, "_vector_search", vector)
    monkeypatch.setattr(inspection, "BM25Plus", lexical)
    # Only account A's PDF matches this query lexically.
    result = inspection.search(cfg, account_catalog, "amberprivate", source_id=source_id, account_id=account_id)
    assert sorted(seen) == ["lexical", "vector"]
    assert {c["id"] for c in result["retrieved_passages"]} == allowed_ids
    assert {c["source"]["id"] for c in result["retrieved_passages"]} == expected_sources
    serialized = json.dumps(result)
    assert all(c["text"] not in serialized for c in excluded)
    assert result["decision"] == "inspection"
    assert result["clinical_evidence"] is False


@pytest.mark.parametrize("account_id", [None, "", "unknown", "account_B"])
def test_private_source_requires_matching_account_before_either_ranker(
        cfg, account_catalog, fake_index, monkeypatch, account_id):
    inspection.build(cfg, account_catalog)
    monkeypatch.setattr(inspection, "_vector_search", forbidden)
    monkeypatch.setattr(inspection, "BM25Plus", forbidden)
    with pytest.raises(ValueError, match="source"):
        inspection.search(cfg, account_catalog, "amberprivate", source_id="archive_a", account_id=account_id)


def test_search_fuses_lexical_and_vector_ranks(cfg, inspection_source, fake_index, monkeypatch):
    write_pdf(cfg["pdf_dir"] / inspection_source["file"], ["Quartz quartz.", "Linen.", "Quartz linen."])
    cfg["retrieval_top_k"] = 3
    catalog = [inspection_source]
    inspection.build(cfg, catalog)
    chunks = inspection.load(cfg, catalog)[0]["chunks"]
    monkeypatch.setattr(inspection, "_vector_search", lambda *args: [chunks[1]["id"], chunks[2]["id"]])
    result = inspection.search(cfg, catalog, "quartz")
    # Page 3 wins because both rankings contain it; pages 1 and 2 each occur in only one ranking.
    assert result["retrieved_passages"][0]["page"] == 3
    assert {c["page"] for c in result["retrieved_passages"]} == {1, 2, 3}


def test_empty_vector_results_cannot_silently_fall_back_to_bm25(cfg, catalog, fake_index, monkeypatch):
    inspection.build(cfg, catalog)
    monkeypatch.setattr(inspection, "_vector_search", lambda *args: ["clinical:v1:0"])
    with pytest.raises(RuntimeError, match="no permitted passages"):
        inspection.search(cfg, catalog, "Amber archive")


@pytest.mark.parametrize("only_inspection", [False, True])
def test_clinical_retrieval_filters_inspection_ids(cfg, store, indexed, monkeypatch, only_inspection):
    clinical_ids = {c["id"] for c in store.chunks()}
    foreign = "inspection:us_archive:fixture:p1:0"
    returned = [foreign] if only_inspection else [foreign, *clinical_ids]
    monkeypatch.setattr(graph, "vector_search", lambda *args: returned)
    if only_inspection:
        with pytest.raises(retrieval.RetrievalNotReady, match="no eligible passages"):
            retrieval.retrieve(cfg, store, "monitoring information")
    else:
        passages, _, _ = retrieval.retrieve(cfg, store, "monitoring information")
        assert {c["id"] for c in passages} == clinical_ids
        assert all(not c["id"].startswith("inspection:") for c in passages)


@pytest.mark.parametrize("command", ["index-all", "inspect"])
@pytest.mark.parametrize("fails", [False, True])
def test_cli_inspection_dispatch_never_initializes_clinical_store(cfg, catalog, monkeypatch, capsys, command, fails):
    calls = []
    selected = catalog[-1]["id"]
    query = "Neutral archive inventory"
    expected = ({"ready": True, "expected_chunks": 9} if command == "index-all" else
                {"decision": "inspection", "clinical_evidence": False, "retrieved_passages": []})

    def complete():
        if fails:
            raise RuntimeError("Synthetic inspection failure")
        return expected

    def build(config, sources):
        assert config is cfg and sources is catalog
        calls.append("index-all")
        return complete()

    def search(config, sources, question, source_id=None, account_id=None):
        assert config is cfg and sources is catalog
        assert question == query and source_id == selected
        assert account_id is None
        calls.append("inspect")
        return complete()

    monkeypatch.setattr(cli, "settings", lambda: cfg)
    monkeypatch.setattr(cli, "sources", lambda config: catalog)
    monkeypatch.setattr(cli, "Store", forbidden)
    monkeypatch.setattr(inspection, "build", build)
    monkeypatch.setattr(inspection, "search", search)
    argv = ["camzyos", command]
    if command == "inspect":
        argv += ["--query", query, "--source", selected]
    monkeypatch.setattr(sys, "argv", argv)
    if fails:
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 1
    else:
        cli.main()
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    if fails:
        assert output["command"] == command and output["error"] == "RuntimeError"
    else:
        assert output == expected
    assert captured.err == ""
    assert calls == [command]
    assert not (cfg["data_dir"] / "app.sqlite").exists()


def test_real_catalog_all_eight_pdfs_prepare_offline(cfg, monkeypatch):
    catalog = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))["sources"]
    assert len(catalog) == 8
    cfg["pdf_dir"] = ROOT / "assets" / "product_information"
    monkeypatch.setattr(inspection, "index_chunks", forbidden)
    documents = [inspection.prepare_source(cfg, source) for source in catalog]
    assert {d["source_id"] for d in documents} == {s["id"] for s in catalog}
    assert {d["source_id"] for d in documents if d["source"]["market"] == "US"} == {"us_fda", "us_bms"}
    assert any(d["source"]["audience"] == "public" for d in documents)
    for document in documents:
        assert_page_coverage(document, cfg["pdf_dir"] / document["file"])
        assert document["page_count"] == len(document["pages"])
        text_pages = set(document["pages_with_text"])
        blank_pages = set(document["no_text_pages"])
        assert text_pages.isdisjoint(blank_pages)
        assert text_pages | blank_pages == set(range(1, document["page_count"] + 1))
        assert {c["page"] for c in document["chunks"]} == text_pages
        assert len(document["audit"]) == document["page_count"]
        assert document["chunk_count"] == len(document["chunks"]) > 0
        for chunk in document["chunks"]:
            assert chunk["id"].startswith("inspection:")
            assert chunk["corpus"] == "inspection"
            assert chunk["clinical_evidence"] is False
            assert chunk["requires_review"] is (chunk["page"] in document["review_pages"])
    eu = next(d for d in documents if d["source_id"] == "eu_smpc")
    assert {4, 5, 6, 7} <= set(eu["review_pages"]) & set(eu["pages_with_text"])
    assert any(page > eu["source"]["pages"][1] for page in eu["pages_with_text"])
    assert len(version_files(cfg)) == 8
    assert not manifest_path(cfg).exists()
    assert not (cfg["data_dir"] / "app.sqlite").exists()
