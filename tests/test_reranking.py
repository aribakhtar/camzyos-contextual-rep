import copy

import pytest
from pydantic import ValidationError

from camzyos import graph, reranking, retrieval


def passages(count=3):
    return [{"id": f"p{i}", "text": f"Synthetic retrieval fixture {i}", "version_id": "fixture",
             "source": {"title": "Fixture", "eligible": True}} for i in range(count)]


def test_reranker_reorders_original_passages_and_keeps_stable_ties(cfg, monkeypatch):
    original = passages()
    before = copy.deepcopy(original)
    monkeypatch.setattr(reranking, "structured", lambda *a, **kw: reranking.Ranking(scores=[
        reranking.PassageScore(passage_id="p0", relevance=0, reason="unrelated"),
        reranking.PassageScore(passage_id="p1", relevance=3, reason="relevant"),
        reranking.PassageScore(passage_id="p2", relevance=3, reason="relevant")]))
    ranked = reranking.rerank(cfg, "fixture query", original)
    assert [p["id"] for p in ranked] == ["p1", "p2", "p0"]
    assert ranked[0]["retrieval"]["candidate_rank"] == 2
    assert ranked[0]["retrieval"]["reranked_rank"] == 1
    assert original == before
    assert all({k:v for k,v in p.items() if k != "retrieval"} == before[int(p["id"][1:])] for p in ranked)


@pytest.mark.parametrize("ids", [["p0", "p1"], ["p0", "p1", "foreign"], ["p0", "p0", "p2"]])
def test_bad_ranking_ids_cannot_add_replace_or_duplicate_evidence(cfg, monkeypatch, ids):
    monkeypatch.setattr(reranking, "structured", lambda *a, **kw: reranking.Ranking(scores=[
        reranking.PassageScore(passage_id=i, relevance=3, reason="fixture") for i in ids]))
    with pytest.raises(ValueError, match="exactly"):
        reranking.rerank(cfg, "fixture", passages())


def test_inspection_passages_rejected_before_reranker_call(cfg, monkeypatch):
    monkeypatch.setattr(reranking, "structured", lambda *a, **kw: pytest.fail("No call permitted"))
    with pytest.raises(ValueError, match="Inspection"):
        reranking.rerank(cfg, "fixture", [{**passages()[0], "id": "inspection:fixture"}])


def test_reranker_schema_constrains_passage_ids_and_candidate_count(cfg, monkeypatch):
    def check_schema(config, schema, instruction, payload, **kwargs):
        rows = [{"passage_id": p["id"], "relevance": 2, "reason": "Fixture"} for p in payload["passages"]]
        parsed = schema.model_validate({"scores": rows})
        with pytest.raises(ValidationError):
            schema.model_validate({"scores": [{**rows[0], "passage_id": "foreign"}] + rows[1:]})
        with pytest.raises(ValidationError):
            schema.model_validate({"scores": rows[:-1]})
        return parsed
    monkeypatch.setattr(reranking, "structured", check_schema)
    assert len(reranking.rerank(cfg, "fixture", passages())) == 3


class ScopedStore:
    def __init__(self):
        self.allowed = passages(8)
        self.scopes = []

    def chunks(self, account=None):
        self.scopes.append(account)
        return self.allowed


def test_candidate_pool_is_expanded_before_final_k_and_foreign_ids_are_filtered(cfg, monkeypatch, indexed):
    cfg.update(reranking_enabled=True, retrieval_top_k=2, retrieval_candidate_k=8)
    store = ScopedStore()
    seen = {}
    def vector(config, question, chunks):
        seen["vector_k"] = config["retrieval_top_k"]
        return ["foreign", "inspection:x"] + [p["id"] for p in chunks]
    def rank(config, query, candidates):
        seen["ids"] = [c["id"] for c in candidates]
        return list(reversed(candidates))
    monkeypatch.setattr(graph, "vector_search", vector)
    monkeypatch.setattr(retrieval, "rerank", rank)
    result, backend, warnings = retrieval.retrieve(cfg, store, "fixture", "ACCOUNT_A")
    assert seen["vector_k"] == 8 and len(seen["ids"]) == 8
    assert "foreign" not in seen["ids"] and "inspection:x" not in seen["ids"]
    assert len(result) == 2 and "reranking" in backend and not warnings
    assert store.scopes == ["ACCOUNT_A", "ACCOUNT_A"]


def test_reranker_failure_is_visible_and_preserves_hybrid_order(cfg, monkeypatch, indexed):
    cfg.update(reranking_enabled=True, retrieval_top_k=2, retrieval_candidate_k=8)
    store = ScopedStore()
    def fail(*args):
        raise TimeoutError("sk-secret")
    monkeypatch.setattr(retrieval, "rerank", fail)
    result, backend, warnings = retrieval.retrieve(cfg, store, "fixture")
    assert len(result) == 2 and backend == "Neo4j vector + BM25"
    assert len(warnings) == 1 and "TimeoutError" in warnings[0] and "sk-secret" not in warnings[0]


def test_withdrawal_during_reranking_blocks_use(cfg, monkeypatch, indexed):
    cfg.update(reranking_enabled=True, retrieval_top_k=2, retrieval_candidate_k=8)
    store = ScopedStore()
    def withdraw(config, query, candidates):
        store.allowed = []
        return candidates
    monkeypatch.setattr(retrieval, "rerank", withdraw)
    with pytest.raises(retrieval.RetrievalNotReady, match="eligibility changed"):
        retrieval.retrieve(cfg, store, "fixture")
