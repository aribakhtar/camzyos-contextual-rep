import re

from rank_bm25 import BM25Plus

from camzyos import graph


def tokens(text):
    return re.findall(r"[\wäöüß]+", text.casefold())


def retrieve(cfg, store, question, account_id=None):
    chunks = store.chunks(account_id)
    if not chunks:
        return [], "none", []
    corpus = [tokens(c["text"]) for c in chunks]
    query_tokens = set(tokens(question))
    scores = BM25Plus(corpus).get_scores(list(query_tokens))
    lexical = [chunks[i]["id"] for i in sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
               if query_tokens.intersection(corpus[i])][:cfg["retrieval_top_k"] * 2]
    warnings, vector, backend = [], [], "BM25 (local eligible passages)"
    if cfg["api_key"] and cfg["neo4j_password"]:
        try:
            vector = graph.vector_search(cfg, question, chunks)
            if vector:
                backend = "Neo4j vector + BM25"
            else:
                warnings.append("Vector search returned no eligible passages; used local BM25.")
        except Exception as exc:
            warnings.append(f"Vector retrieval unavailable ({type(exc).__name__}); used local BM25.")
    # Reciprocal rank fusion; both inputs are already scoped, and membership is checked again.
    ranked = {}
    allowed = {c["id"]: c for c in chunks}
    for ranking in (lexical, vector):
        for rank, cid in enumerate(ranking):
            if cid in allowed:
                ranked[cid] = ranked.get(cid, 0) + 1 / (60 + rank)
    selected = sorted(ranked, key=ranked.get, reverse=True)[:cfg["retrieval_top_k"]]
    return [allowed[cid] for cid in selected], backend, warnings
