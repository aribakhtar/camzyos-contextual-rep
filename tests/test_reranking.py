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
    monkeypatch.setattr(reranking, "structured", lambda cfg, schema, *a, **kw: schema(
        candidate_0={"relevance": 0, "reason": "unrelated"},
        candidate_1={"relevance": 3, "reason": "relevant"},
        candidate_2={"relevance": 3, "reason": "relevant"}))
    ranked = reranking.rerank(cfg, "fixture query", original)
    assert [p["id"] for p in ranked] == ["p1", "p2", "p0"]
    assert ranked[0]["retrieval"]["candidate_rank"] == 2
    assert ranked[0]["retrieval"]["reranked_rank"] == 1
    assert original == before
    assert all({k:v for k,v in p.items() if k != "retrieval"} == before[int(p["id"][1:])] for p in ranked)


@pytest.mark.parametrize("slots", [["candidate_0", "candidate_1"],
    ["candidate_0", "candidate_1", "foreign"], ["candidate_0", "candidate_0", "candidate_2"]])
def test_bad_ranking_slots_cannot_add_replace_or_duplicate_evidence(cfg, monkeypatch, slots):
    def invalid(cfg, schema, *args, **kwargs):
        return schema.model_validate({slot: {"relevance": 3, "reason": "fixture"} for slot in slots})
    monkeypatch.setattr(reranking, "structured", invalid)
    with pytest.raises(ValidationError):
        reranking.rerank(cfg, "fixture", passages())


def test_inspection_passages_rejected_before_reranker_call(cfg, monkeypatch):
    monkeypatch.setattr(reranking, "structured", lambda *a, **kw: pytest.fail("No call permitted"))
    with pytest.raises(ValueError, match="Inspection"):
        reranking.rerank(cfg, "fixture", [{**passages()[0], "id": "inspection:fixture"}])


def test_reranker_schema_requires_each_candidate_and_preserves_mapping(cfg, monkeypatch):
    def check_schema(config, schema, instruction, payload, **kwargs):
        rows = {p["slot"]: {"relevance": 2, "reason": "Fixture"} for p in payload["passages"]}
        assert set(schema.model_json_schema()["required"]) == set(rows)
        assert all(p["text"] == f"Synthetic retrieval fixture {i}" for i, p in enumerate(payload["passages"]))
        parsed = schema.model_validate(rows)
        with pytest.raises(ValidationError):
            schema.model_validate({**rows, "foreign": rows["candidate_0"]})
        with pytest.raises(ValidationError):
            schema.model_validate({k: v for k, v in rows.items() if k != "candidate_2"})
        return parsed
    monkeypatch.setattr(reranking, "structured", check_schema)
    assert len(reranking.rerank(cfg, "fixture", passages())) == 3


def test_duplicate_candidates_rejected_before_model_call(cfg, monkeypatch):
    monkeypatch.setattr(reranking, "structured", lambda *a, **kw: pytest.fail("No call permitted"))
    with pytest.raises(ValueError, match="unique"):
        reranking.rerank(cfg, "fixture", [passages()[0], passages()[0]])
    assert reranking.rerank(cfg, "fixture", []) == []


@pytest.mark.parametrize("score", [
    {"relevance": -1, "reason": "invalid"}, {"relevance": 4, "reason": "invalid"},
    {"relevance": 2, "reason": "x" * 161}, {"relevance": 2, "reason": "valid", "passage_id": "foreign"}])
def test_score_limits_and_model_supplied_ids_are_enforced(score):
    with pytest.raises(ValidationError):
        reranking.PassageScore.model_validate(score)


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
