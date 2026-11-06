"""Chat retrieval over every prepared PDF, preserving source scope and extraction flags."""
from camzyos import guardrails, inspection
from camzyos.reranking import rerank
from camzyos.settings import sources
from camzyos.store import within_pages


def enabled(cfg):
    return cfg.get("retrieval_scope", "clinical") == "all_documents"


def chunks(cfg, account_id=None):
    return [chunk for document in inspection.load(cfg, sources(cfg)) for chunk in document["chunks"]
            if not guardrails.source_rules(chunk["source"], cfg, account_id)
            and within_pages(chunk, chunk["source"])]


def status(cfg, account_id=None):
    report = inspection.report(cfg, sources(cfg))
    if report["ready"]:
        scoped = chunks(cfg, account_id)
        report = {**report, "eligible_chunks": len(scoped),
                  "eligible_document_count": len({c["source"]["id"] for c in scoped})}
    return {**report, "eligible_chunks": report.get("eligible_chunks", 0), "scope": "all_documents"}


def validate_passages(cfg, passages, account_id=None):
    """Reject stale, modified or differently owned text after external reranking."""
    current = {c["id"]: c for c in chunks(cfg, account_id)}
    fields = ("text", "source", "version_id", "page", "page_end", "corpus",
              "clinical_evidence", "requires_review")
    return all(p["id"] in current and all(p.get(key) == current[p["id"]].get(key) for key in fields)
               for p in passages)


def retrieve(cfg, question, account_id=None):
    from camzyos.retrieval import tokens
    top_k = cfg["retrieval_top_k"]
    candidate_k = max(top_k, cfg.get("retrieval_candidate_k", top_k))
    permitted = chunks(cfg, account_id)
    if not permitted:
        return [], "All-PDF Neo4j vector + BM25", []
    result = inspection.search({**cfg, "retrieval_top_k": candidate_k}, sources(cfg), question,
                               account_id=account_id, allowed_ids={c["id"] for c in permitted})
    query_tokens = set(tokens(question))
    passages = [{**p, "retrieval": {"keyword_matches": len(query_tokens.intersection(tokens(p["text"])))}}
                for p in result["retrieved_passages"]]
    backend, warnings = "All-PDF Neo4j vector + BM25", []
    if cfg.get("reranking_enabled") and passages:
        try:
            passages = rerank(cfg, question, passages)
            backend += " + LLM relevance reranking"
        except Exception as exc:
            warnings.append(f"Relevance scoring unavailable ({type(exc).__name__}); GR_15 requires human review.")
            from camzyos.retrieval import RetrievalConfidenceUnavailable
            raise RetrievalConfidenceUnavailable(warnings[-1]) from exc
    if not validate_passages(cfg, passages, account_id):
        raise RuntimeError("PDF content or source access changed during retrieval; retry.")
    return guardrails.above_threshold(cfg, passages)[:top_k], backend, warnings
