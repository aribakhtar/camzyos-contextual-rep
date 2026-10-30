"""Live all-PDF indexing/retrieval smoke checks; not a clinical-answer benchmark."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from camzyos import inspection
from camzyos.retrieval import retrieve
from camzyos.settings import settings, sources
from camzyos.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cfg = settings()
    catalog = sources(cfg)
    store = Store(cfg["data_dir"])
    documents = inspection.load(cfg, catalog)
    snapshot = [d["checksum"] for d in documents]
    clinical = store.chunks(all_accounts=True)
    # The clinical request below uses the public/general scope, not all_accounts.
    allowed = {c["id"] for c in store.chunks()}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = args.output or Path("reports") / f"all-pdf-smoke-{stamp}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    with path.open("w", encoding="utf-8") as output:
        for document in documents:
            reference = max(document["chunks"], key=lambda c: len(c["text"]))
            query = reference["text"][:600]
            record = {"source_id": document["source_id"], "version_id": document["version_id"],
                      "reference_id": reference["id"], "query": query, "successful": False,
                      "test_kind": "exact-passage retrieval smoke; not clinical quality",
                      "model": cfg["embedding_model"], "embedding_dimensions": cfg["embedding_dimensions"],
                      "time": datetime.now(timezone.utc).isoformat(), "answer_generated": False}
            try:
                if [d["checksum"] for d in inspection.load(cfg, catalog)] != snapshot:
                    raise RuntimeError("Inspection corpus changed during the suite.")
                result = inspection.search(cfg, catalog, query, document["source_id"])
                retrieved = result["retrieved_passages"]
                ids = [c["id"] for c in retrieved]
                rank = ids.index(reference["id"]) + 1 if reference["id"] in ids else None
                clinical_result, _, _ = retrieve(cfg, store, query)
                isolated = all(c["id"] in allowed and not c["id"].startswith("inspection:")
                               for c in clinical_result)
                correct_source = bool(retrieved) and all(c["source"]["id"] == document["source_id"]
                                                         for c in retrieved)
                record.update(inspection_result=result, reference_rank=rank,
                              clinical_result_ids=[c["id"] for c in clinical_result],
                              clinical_source_ids=sorted({c["source"]["id"] for c in clinical_result}),
                              clinical_isolation_passed=isolated,
                              successful=rank is not None and isolated and correct_source)
                if (store.chunks(all_accounts=True) != clinical
                        or [d["checksum"] for d in inspection.load(cfg, catalog)] != snapshot):
                    raise RuntimeError("Corpus changed during the suite.")
            except Exception as exc:
                record.update(successful=False, error=type(exc).__name__)
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            failed |= not record["successful"]
            print(json.dumps({"source": document["source_id"], "successful": record["successful"],
                              "reference_rank": record.get("reference_rank"), "error": record.get("error")}),
                  flush=True)
    print("Report:", path)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
