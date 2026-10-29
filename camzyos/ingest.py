import hashlib
import json
import shutil
from pathlib import Path

import httpx

from camzyos.documents import digest, extract, soft_chunks


def process(cfg, store, source, path=None):
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

