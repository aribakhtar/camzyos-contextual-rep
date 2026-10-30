"""All-PDF retrieval for local testing/review; never a clinical-answer evidence source.

The fixed Neo4j label/index and inspection: IDs are deliberately separate from
CamzyosChunk. Staged, US, public, historical and structured text stays inspectable
without activating it or changing any clinical eligibility rule.
"""
import hashlib
import json
import math
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pymupdf
import pysbd
from openai import OpenAI
from rank_bm25 import BM25Plus

from camzyos import graph
from camzyos.documents import digest, extract
from camzyos.retrieval import tokens

INDEX = "camzyos_inspection_embeddings"
SCHEMA = 1


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _identity(cfg, source, path=None):
    if path is not None:
        resolved = Path(path)
    else:
        resolved = cfg["pdf_dir"] / source["file"]
        if not resolved.is_file():
            resolved = cfg["data_dir"] / "public" / source["file"]
    if not resolved.is_file():
        raise FileNotFoundError("Missing PDF for source " + source["id"])
    sha = digest(resolved)
    fingerprint = _hash({"schema": SCHEMA, "source": source, "target": cfg["chunk_target_chars"],
                         "overlap": cfg["chunk_overlap_sentences"]})[:16]
    return resolved, sha, f"inspection:{source['id']}:{sha[:16]}:{fingerprint}"


def _check_document(document):
    payload = {key: value for key, value in document.items() if key != "checksum"}
    if document.get("checksum") != _hash(payload):
        raise ValueError("Inspection document checksum mismatch; rebuild the corpus.")
    chunks = document["chunks"]
    if len(chunks) != document["chunk_count"] or not chunks:
        raise ValueError("Inspection document has no complete text coverage.")
    if len({c["id"] for c in chunks}) != len(chunks):
        raise ValueError("Duplicate inspection passage IDs.")
    for chunk in chunks:
        if (chunk["corpus"] != "inspection" or chunk["clinical_evidence"] is not False
                or chunk["version_id"] != document["version_id"]
                or not chunk["id"].startswith(document["version_id"] + ":")
                or not chunk["text"].strip()):
            raise ValueError("Invalid inspection passage provenance.")
    pages = document["pages"]
    if [p["page"] for p in pages] != list(range(1, document["page_count"] + 1)):
        raise ValueError("Inspection page inventory is incomplete.")
    if sorted(p["page"] for p in pages if p["text"].strip()) != document["pages_with_text"]:
        raise ValueError("Inspection text-page inventory is incomplete.")
    for page in pages:
        end = 0
        for chunk in sorted((c for c in chunks if c["page"] == page["page"]), key=lambda c: c["char_start"]):
            start, stop = chunk["char_start"], chunk["char_end"]
            if (not 0 <= start < stop <= len(page["text"]) or chunk["page_end"] != page["page"]
                    or page["text"][start:stop] != chunk["text"] or page["text"][end:start].strip()):
                raise ValueError("Inspection chunks do not preserve the page text.")
            end = max(end, stop)
        if page["text"][end:].strip():
            raise ValueError("Inspection page text was dropped.")


def _page_chunks(page, source, version, target, overlap):
    """Retain all nonempty page text, even short/structured pages; mark for review.

    Unlike clinical soft_chunks(), no page is suppressed by eligibility or layout.
    No interpretation of table cells, diagram arrows or clinical claims is added.
    """
    text = page["text"]
    if not text.strip():
        return []
    language = source.get("language", "en")
    segmenter = pysbd.Segmenter(language=language if language in {"en", "de"} else "en",
                               clean=False, char_span=True)
    sentences = segmenter.segment(text)
    boundaries = [0] + [s.start for s in sentences[1:]] + [len(text)]
    spans = list(zip(boundaries, boundaries[1:]))
    groups, group, size = [], [], 0
    for first, last in spans:
        if group and size + last - first > target:
            groups.append(group)
            group = group[-overlap:] if overlap and len(group) > overlap else []
            size = sum(end - start for start, end in group)
        group.append((first, last))
        size += last - first
    if group:
        groups.append(group)
    result = []
    for group in groups:
        raw = text[group[0][0]:group[-1][1]]
        first = group[0][0] + len(raw) - len(raw.lstrip())
        last = group[-1][1] - len(raw) + len(raw.rstrip())
        body = text[first:last]
        if body:
            result.append({"id": f"{version}:p{page['page']}:{len(result)}", "version_id": version,
                           "source": source, "text": body, "page": page["page"], "page_end": page["page"],
                           "char_start": first, "char_end": last,
                           "section": "Unreviewed page text for inspection", "corpus": "inspection",
                           "clinical_evidence": False, "requires_review": page["requires_review"]})
    return result


def prepare_source(cfg, source, path=None):
    resolved, sha, version = _identity(cfg, source, path)
    artifact = cfg["data_dir"] / "inspection" / "versions" / (_hash(version) + ".json")
    if artifact.is_file():
        document = json.loads(artifact.read_text(encoding="utf-8"))
        _check_document(document)
        if document["version_id"] != version:
            raise ValueError("Inspection version mismatch.")
        return document
    scan_source = {key: value for key, value in source.items() if key != "pages"}
    pages, audit = extract(resolved, scan_source)
    # Inspection retains raw extracted text as well as the cleanup audit. Even
    # title/footer-only and diagram pages remain searchable for extraction tests.
    with pymupdf.open(resolved) as pdf:
        for page, raw_page in zip(pages, pdf):
            page["text"] = raw_page.get_text("text", flags=pymupdf.TEXT_DEHYPHENATE)
    if digest(resolved) != sha:
        raise RuntimeError("PDF changed during extraction; rerun preparation.")
    chunks = [chunk for page in pages for chunk in _page_chunks(
        page, source, version, cfg["chunk_target_chars"], cfg["chunk_overlap_sentences"])]
    counts = Counter(c["page"] for c in chunks)
    for entry in audit:
        entry["inspection_chunks"] = counts[entry["page"]]
        raw_text = pages[entry["page"] - 1]["text"]
        entry["raw_text_chars"] = len(raw_text)
        entry["raw_text_sha256"] = hashlib.sha256(raw_text.encode()).hexdigest()
    # Preserve the exact input for page-by-page extraction review and reproducibility.
    snapshot = cfg["data_dir"] / "snapshots" / (sha + ".pdf")
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if not snapshot.exists():
        shutil.copyfile(resolved, snapshot)
    if digest(snapshot) != sha:
        raise ValueError("PDF snapshot checksum mismatch.")
    document = {"source_id": source["id"], "source": source, "file": source["file"], "sha256": sha,
                "version_id": version, "page_count": len(pages), "chunk_count": len(chunks),
                "pages_with_text": sorted(counts), "no_text_pages": [p["page"] for p in pages
                                                                          if not p["text"].strip()],
                "review_pages": [p["page"] for p in pages if p["requires_review"]],
                "snapshot": str(snapshot), "audit": audit, "pages": pages, "chunks": chunks}
    document["checksum"] = _hash(document)
    _check_document(document)
    _write(artifact, document)
    return document


def _manifest_path(cfg):
    return cfg["data_dir"] / "inspection" / "manifest.json"


def load(cfg, catalog):
    manifest = json.loads(_manifest_path(cfg).read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValueError("Inspection schema changed; rebuild the corpus.")
    documents = manifest["documents"]
    expected = {s["id"]: s for s in catalog}
    if not expected or len(expected) != len(catalog) or len(documents) != len(expected):
        raise ValueError("Incomplete inspection catalog; rebuild the corpus.")
    if {d["source_id"] for d in documents} != set(expected):
        raise ValueError("Inspection sources changed; rebuild the corpus.")
    for document in documents:
        _check_document(document)
        _, _, version = _identity(cfg, expected[document["source_id"]])
        if version != document["version_id"]:
            raise ValueError("Inspection PDF or configuration changed; rebuild source " + document["source_id"])
    return documents


def index_status(cfg, chunks):
    result = {"ready": False, "index_name": INDEX, "expected_chunks": len(chunks), "indexed_chunks": 0,
              "index_state": "missing", "missing_ids": [c["id"] for c in chunks]}
    if not chunks:
        return result
    try:
        with graph.driver(cfg) as db:
            indexes = db.execute_query("SHOW VECTOR INDEXES YIELD name,state,options,labelsOrTypes,properties "
                                       "WHERE name=$index RETURN state,options,labelsOrTypes,properties", index=INDEX,
                                       database_=cfg["neo4j_database"]).records
            if not indexes:
                return result
            result["index_state"] = indexes[0]["state"]
            if (indexes[0]["labelsOrTypes"] != ["CamzyosInspectionChunk"]
                    or indexes[0]["properties"] != ["embedding"]):
                result["index_state"] = "incompatible index schema"
                return result
            options = indexes[0]["options"]["indexConfig"]
            if options.get("vector.dimensions") != cfg["embedding_dimensions"]:
                result["index_state"] = "incompatible dimensions"
                return result
            if str(options.get("vector.similarity_function", "")).casefold() != "cosine":
                result["index_state"] = "incompatible similarity"
                return result
            rows = db.execute_query("MATCH(c:CamzyosInspectionChunk) WHERE c.id IN $ids "
                                    "AND c.corpus='inspection' AND c.clinical_evidence=false "
                                    "AND c.embedding_model=$model AND size(c.embedding)=$dimensions "
                                    "RETURN c.id AS id,c.text AS text,c.version_id AS version_id,"
                                    "c.source_id AS source_id,c.page AS page", ids=result["missing_ids"],
                                    model=cfg["embedding_model"], dimensions=cfg["embedding_dimensions"],
                                    database_=cfg["neo4j_database"]).records
        expected = {c["id"]: (c["text"], c["version_id"], c["source"]["id"], c["page"]) for c in chunks}
        present = {row["id"] for row in rows if expected.get(row["id"]) == (
            row["text"], row["version_id"], row["source_id"], row["page"])}
        result.update(indexed_chunks=len(present), missing_ids=sorted(set(expected) - present))
        result["ready"] = result["index_state"] == "ONLINE" and not result["missing_ids"]
    except Exception as exc:
        result.update(index_state="unavailable", error=type(exc).__name__)
    return result


def index_chunks(cfg, chunks):
    if not cfg["api_key"]:
        raise ValueError("Set OPENAI_API_KEY locally before indexing PDFs.")
    if not chunks or any(c.get("corpus") != "inspection" or c.get("clinical_evidence") is not False
                         or not c["id"].startswith("inspection:") for c in chunks):
        raise ValueError("Only inspection passages belong in this index.")
    before = index_status(cfg, chunks)
    if before["index_state"].startswith("incompatible"):
        raise ValueError("Inspection index configuration differs; migrate this index explicitly.")
    if before["ready"]:
        return {**before, "new_embeddings": 0}
    missing = set(before["missing_ids"])
    pending = [c for c in chunks if c["id"] in missing]
    with graph.driver(cfg) as db:
        db.execute_query("CREATE CONSTRAINT camzyos_inspection_chunk_id IF NOT EXISTS "
                         "FOR (c:CamzyosInspectionChunk) REQUIRE c.id IS UNIQUE",
                         database_=cfg["neo4j_database"])
        db.execute_query("CREATE VECTOR INDEX camzyos_inspection_embeddings IF NOT EXISTS "
                         "FOR (c:CamzyosInspectionChunk) ON (c.embedding) OPTIONS {indexConfig: {"
                         "`vector.dimensions`: $dimensions, `vector.similarity_function`: 'cosine'}}",
                         dimensions=cfg["embedding_dimensions"], database_=cfg["neo4j_database"])
        with OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=60, max_retries=2) as client:
            for start in range(0, len(pending), 32):
                batch = pending[start:start + 32]
                response = client.embeddings.create(input=[c["text"] for c in batch],
                    model=cfg["embedding_model"], dimensions=cfg["embedding_dimensions"])
                data = sorted(response.data, key=lambda item: item.index)
                if [item.index for item in data] != list(range(len(batch))):
                    raise ValueError("Embedding response does not match the input batch.")
                rows = []
                for chunk, item in zip(batch, data):
                    if len(item.embedding) != cfg["embedding_dimensions"] or not all(
                            math.isfinite(value) for value in item.embedding):
                        raise ValueError("Invalid inspection embedding dimensions or values.")
                    rows.append({"id": chunk["id"], "text": chunk["text"], "version_id": chunk["version_id"],
                                 "source_id": chunk["source"]["id"], "page": chunk["page"],
                                 "requires_review": chunk["requires_review"], "embedding": item.embedding})
                db.execute_query("UNWIND $rows AS row MERGE(c:CamzyosInspectionChunk {id:row.id}) "
                                 "SET c += row,c.embedding_model=$model,c.corpus='inspection',"
                                 "c.clinical_evidence=false", rows=rows, model=cfg["embedding_model"],
                                 database_=cfg["neo4j_database"])
        db.execute_query("CALL db.awaitIndex($index, 60)", index=INDEX, database_=cfg["neo4j_database"])
    result = index_status(cfg, chunks)
    if not result["ready"]:
        raise RuntimeError("Inspection indexing incomplete: " + result["index_state"])
    return {**result, "new_embeddings": len(pending)}


def build(cfg, catalog):
    if not catalog or len({s["id"] for s in catalog}) != len(catalog):
        raise ValueError("A nonempty unique source catalog is required.")
    documents = [prepare_source(cfg, source) for source in catalog]
    result = index_chunks(cfg, [c for d in documents for c in d["chunks"]])
    if not result["ready"]:
        raise RuntimeError("Inspection index is not ready; existing manifest retained.")
    # Do not publish a run whose inputs changed during parsing/embedding.
    for document, source in zip(documents, catalog):
        if _identity(cfg, source)[2] != document["version_id"]:
            raise RuntimeError("PDFs changed during indexing; rerun preparation.")
    _write(_manifest_path(cfg), {"schema": SCHEMA, "built_at": datetime.now(timezone.utc).isoformat(),
                                "documents": documents})
    final = report(cfg, catalog)
    if not final["ready"]:
        raise RuntimeError("Inspection readiness changed after indexing; rerun the build.")
    return {**final, "new_embeddings": result["new_embeddings"]}


def report(cfg, catalog):
    try:
        documents = load(cfg, catalog)
        status = index_status(cfg, [c for d in documents for c in d["chunks"]])
        missing = set(status["missing_ids"])
        rows = [{key: document[key] for key in ("source_id", "file", "version_id", "page_count",
                                                "chunk_count", "no_text_pages", "review_pages")}
                | {"indexed_chunks": sum(c["id"] not in missing for c in document["chunks"]),
                   "text_pages_indexed": sum(all(c["id"] not in missing for c in document["chunks"]
                                                 if c["page"] == page) for page in document["pages_with_text"]),
                   "text_pages_expected": len(document["pages_with_text"]), "clinical_evidence": False}
                for document in documents]
        return {**status, "documents": rows, "document_count": len(documents), "errors": []}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"ready": False, "index_name": INDEX, "index_state": "missing or stale manifest",
                "expected_chunks": 0, "indexed_chunks": 0, "missing_ids": [], "documents": [],
                "document_count": 0, "errors": [type(exc).__name__]}


def _vector_search(cfg, question, chunks):
    from neo4j_graphrag.embeddings import OpenAIEmbeddings
    from neo4j_graphrag.retrievers import VectorRetriever
    with graph.driver(cfg) as db:
        retriever = VectorRetriever(db, INDEX, neo4j_database=cfg["neo4j_database"],
            embedder=OpenAIEmbeddings(model=cfg["embedding_model"], api_key=cfg["api_key"],
                                     base_url=cfg["base_url"]), return_properties=["id", "text"])
        vector = retriever.embedder.embed_query(question, dimensions=cfg["embedding_dimensions"])
        response = retriever.get_search_results(query_vector=vector, top_k=cfg["retrieval_top_k"],
            filters={"version_id": {"$in": sorted({c["version_id"] for c in chunks})},
                     "embedding_model": cfg["embedding_model"], "corpus": "inspection",
                     "clinical_evidence": False})
        return [row["node"]["id"] for row in response.records]


def search(cfg, catalog, question, source_id=None, account_id=None):
    if not question.strip():
        raise ValueError("An inspection query is required.")
    documents = load(cfg, catalog)
    all_chunks = [c for d in documents for c in d["chunks"]]
    if not index_status(cfg, all_chunks)["ready"]:
        raise RuntimeError("Inspection index is not ready; run index-all before testing.")
    chunks = [c for c in all_chunks if (not source_id or c["source"]["id"] == source_id)
              and (not c["source"].get("account_id") or c["source"]["account_id"] == account_id)]
    if not chunks:
        raise ValueError("Unknown or empty inspection source.")
    allowed = {c["id"]: c for c in chunks}
    vector = [cid for cid in _vector_search(cfg, question, chunks) if cid in allowed]
    if not vector:
        raise RuntimeError("Inspection vector search returned no permitted passages.")
    corpus = [tokens(c["text"]) for c in chunks]
    query = set(tokens(question))
    scores = BM25Plus(corpus).get_scores(list(query))
    lexical = [chunks[i]["id"] for i in sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
               if query.intersection(corpus[i])][:cfg["retrieval_top_k"] * 2]
    ranks = {}
    for ranking in (lexical, vector):
        for rank, cid in enumerate(ranking):
            ranks[cid] = ranks.get(cid, 0) + 1 / (60 + rank)
    selected = sorted(ranks, key=ranks.get, reverse=True)[:cfg["retrieval_top_k"]]
    if [d["checksum"] for d in load(cfg, catalog)] != [d["checksum"] for d in documents]:
        raise RuntimeError("Inspection corpus changed during retrieval; rerun the test.")
    return {"decision": "inspection", "clinical_evidence": False, "answer_generated": False,
            "query": question, "source_id": source_id, "index_name": INDEX,
            "corpus_revision": _hash([d["checksum"] for d in documents]),
            "retrieved_passages": [allowed[cid] for cid in selected],
            "limitation": "Unreviewed extraction for testing only; structured page text is not a verified algorithm."}
