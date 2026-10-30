import re

from rank_bm25 import BM25Plus

from camzyos import graph
from camzyos.reranking import rerank


class RetrievalNotReady(RuntimeError):
    pass


def require_index(cfg, chunks):
    readiness = graph.index_status(cfg, chunks)
    if not readiness["ready"]:
        raise RetrievalNotReady("The document index is not ready. Complete document setup before chatting. "
                                f"Indexed {readiness['indexed_chunks']}/{readiness['eligible_chunks']} passages "
                                f"({readiness['index_state']}).")


def tokens(text):
    return re.findall(r"[\wäöüß]+", text.casefold())


def retrieve(cfg, store, question, account_id=None):
    chunks = store.chunks(account_id)
    require_index(cfg, chunks)
    corpus = [tokens(c["text"]) for c in chunks]
    query_tokens = set(tokens(question))
    top_k = cfg["retrieval_top_k"]
    candidate_k = max(top_k, cfg.get("retrieval_candidate_k", top_k)) if cfg.get("reranking_enabled") else top_k
    scores = BM25Plus(corpus).get_scores(list(query_tokens))
    lexical = [chunks[i]["id"] for i in sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
               if query_tokens.intersection(corpus[i])][:candidate_k * 2]
    try:
        vector = graph.vector_search({**cfg, "retrieval_top_k": candidate_k}, question, chunks)
    except Exception as exc:
        raise RetrievalNotReady("Vector retrieval is unavailable; no clinical answer was generated. "
                                "Check the database, model API and document index.") from exc
    allowed = {c["id"]: c for c in chunks}
    vector = [cid for cid in vector if cid in allowed]
    if not vector:
        raise RetrievalNotReady("Vector retrieval returned no eligible passages. Check the document index.")
    # Reciprocal rank fusion; both inputs are already scoped, and membership is checked again.
    ranked = {}
    for ranking in (lexical, vector):
        for rank, cid in enumerate(ranking):
            if cid in allowed:
                ranked[cid] = ranked.get(cid, 0) + 1 / (60 + rank)
    selected = sorted(ranked, key=ranked.get, reverse=True)[:candidate_k]
    candidates = [allowed[cid] for cid in selected]
    backend, warnings = "Neo4j vector + BM25", []
    if cfg.get("reranking_enabled") and len(candidates) > 1:
        try:
            candidates = rerank(cfg, question, candidates)
            backend += " + LLM relevance reranking"
        except Exception as exc:
            warnings.append(f"Reranking unavailable ({type(exc).__name__}); using hybrid retrieval order.")
    # A source withdrawn while reranking must not escape the current eligibility gate.
    current = {c["id"] for c in store.chunks(account_id)}
    if any(p["id"] not in current for p in candidates):
        raise RetrievalNotReady("Source eligibility changed during retrieval. Retry against the current index.")
    return candidates[:top_k], backend, warnings
