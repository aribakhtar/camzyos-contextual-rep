import asyncio
from types import SimpleNamespace

from camzyos import evaluation


def test_reference_rank_scores_missed_and_late_passages():
    scores = evaluation.retrieval_metrics([{"id": "noise"}, {"id": "expected"}], ["expected"])
    assert scores["reference_hit_at_k"] == 1
    assert scores["reciprocal_rank"] == 0.5
    assert evaluation.retrieval_metrics([], ["expected"])["reference_recall_at_k"] == 0


def test_reference_must_match_active_id_and_source_text():
    case = {"reference_ids": ["v1:0"], "reference": "Reference fact."}
    assert evaluation.reference_valid(case, [{"id": "v1:0", "text": "Reference\nfact."}])
    assert not evaluation.reference_valid(case, [{"id": "v2:0", "text": "Reference fact."}])
    assert not evaluation.reference_valid(case, [{"id": "v1:0", "text": "Changed fact."}])


def test_retrieval_only_eval_has_no_answer_or_memory_writes(cfg, store, tables, indexed):
    case = {"id": "test", "question": "monitoring information", "reference_ids": ["v1:0"],
            "reference": store.chunks()[0]["text"]}
    result = evaluation.evaluate(cfg, store, tables, "a@example.test", case, retrieval_only=True)
    assert result["result"]["decision"] == "retrieval"
    assert result["metrics"]["reference_hit_at_k"] == 1
    assert "faithfulness" not in result["metrics"]
    assert store.history("HCP_A") == []


def test_ragas_metric_failure_is_recorded_without_inventing_a_score(cfg, monkeypatch):
    import ragas.llms
    import ragas.metrics.collections
    seen = []

    class Good:
        def __init__(self, **kwargs):
            pass

        async def ascore(self, **kwargs):
            seen.append(kwargs)
            return SimpleNamespace(value=0.5)

    class Bad(Good):
        async def ascore(self, **kwargs):
            raise TimeoutError("Synthetic judge timeout")
    monkeypatch.setattr(ragas.llms, "llm_factory", lambda *a, **k: None)
    monkeypatch.setattr(ragas.metrics.collections, "ContextPrecision", Good)
    monkeypatch.setattr(ragas.metrics.collections, "ContextRecall", Good)
    monkeypatch.setattr(ragas.metrics.collections, "Faithfulness", Bad)
    cfg["api_key"] = "test-placeholder"
    scores, errors, details = asyncio.run(evaluation.score_ragas(cfg, "question", "reference", {
        "decision": "answer", "clinical_response": "claim", "retrieved_evidence": [{"text": "passage"}]}))
    assert scores == {"context_precision": 0.5, "context_recall": 0.5, "faithfulness": None}
    assert errors == {"faithfulness": "TimeoutError"}
    assert all(k["reference"] == "reference" for k in seen)
    assert "faithfulness" not in details
