import hashlib
import json
import shutil
from pathlib import Path

import httpx

from camzyos import graph
from camzyos.documents import digest, extract, soft_chunks
from camzyos.settings import ROOT


def process_document(cfg, store, source, path=None):
    """Offline preparation action: parse, chunk, stage and index; no automatic approval."""
    result = process(cfg, store, source, path)
    if result["status"] == "missing":
        raise FileNotFoundError("The configured PDF was not found.")
    chunks = store.version_chunks(result["version"]) if "version" in result else []
    result["indexed_chunks"] = graph.index_chunks(cfg, chunks) if chunks else 0
    return result


def publish_version(cfg, store, version, note):
    if not note.strip():
        raise ValueError("A review note is required.")
    # Populate immutable new vectors while chat continues to use the previous active version.
    graph.index_chunks(cfg, store.version_chunks(version))
    store.activate(version, note)


def build(cfg, store, catalog):
    """One-time clone setup. Chat never calls this pipeline."""
    prepare_demo(cfg, store, catalog)
    graph.sync_documents(cfg, store)
    return graph.index_status(cfg, store.chunks(all_accounts=True))


def prepare_demo(cfg, store, catalog):
    """Rebuild the bundled demo; only the exact previously reviewed version activates."""
    if not cfg["workbook"].is_file():
        raise FileNotFoundError("The configured HCP workbook is missing.")
    results = [process(cfg, store, source) for source in catalog]
    if any(r["status"] == "missing" for r in results):
        raise FileNotFoundError("One or more configured PDFs are missing; see assets/product_information.")
    reviews = json.loads((ROOT / "assets/demo_review.json").read_text(encoding="utf-8"))["versions"]
    current = {r["version"] for r in results}
    for version in store.versions():
        for review in reviews:
            if (version["id"] in current and version["id"] == review["version_id"]
                    and version["hash"] == review["sha256"]
                    and version["source_id"] == review["source_id"] and version["status"] == "staged"):
                store.activate(version["id"], review["note"])
                next(r for r in results if r["version"] == version["id"])["status"] = "active"
    return results


def process(cfg, store, source, path=None):
    if path is not None and not Path(path).is_file():
        raise FileNotFoundError("The supplied PDF path was not found.")
    path = Path(path) if path else cfg["pdf_dir"] / source["file"]
    if not path.exists():
        path = cfg["data_dir"] / "public" / source["file"]
    if not path.exists():
        return {"source": source["id"], "status": "missing", "chunks": 0}
    content_hash = digest(path)
    pipeline = {"version": 1, "source": source, "target": cfg["chunk_target_chars"],
                "overlap": cfg["chunk_overlap_sentences"]}
    fingerprint = hashlib.sha256(json.dumps(pipeline, sort_keys=True).encode()).hexdigest()[:8]
    version = f"{source['id']}:{content_hash[:16]}:{fingerprint}"
    if previous := next((v for v in store.versions() if v["id"] == version), None):
        return {"source": source["id"], "version": version, "status": previous["status"], "unchanged": True}
    pages, audit = extract(path, source)
    if source["market"] in {"DE", "EU"} and any("Initial U.S. Approval" in p["text"] for p in pages[:3]):
        raise ValueError("US label detected in a source registered for Germany/EU.")
    chunks = soft_chunks(pages, cfg["chunk_target_chars"], cfg["chunk_overlap_sentences"],
                         source.get("language", "en"))
    folder = cfg["data_dir"] / "snapshots"
    folder.mkdir(parents=True, exist_ok=True)
    snapshot = folder / (content_hash + ".pdf")
    if not snapshot.exists():
        shutil.copyfile(path, snapshot)
    status = store.stage(source, version, content_hash, chunks, audit, snapshot)
    return {"source": source["id"], "version": version, "status": status, "chunks": len(chunks),
            "review_pages": [p["page"] for p in audit if p["requires_review"]]}


def fetch_public(cfg, source):
    url = source.get("url", "")
    if not url.startswith(("https://www.ema.europa.eu/", "https://fi.b-ms.de/")):
        raise ValueError("Only configured official EMA/BMS document URLs can be fetched.")
    response = httpx.get(url, timeout=45, follow_redirects=True,
                         headers={"User-Agent": "CAMZYOS-research-prototype/0.1"})
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise ValueError("The source did not return a PDF.")
    folder = cfg["data_dir"] / "public"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / source["file"]
    path.write_bytes(response.content)
    return path

