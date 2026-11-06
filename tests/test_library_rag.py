"""All-document chat must retrieve real library passages without losing source or HCP scope."""
import copy
import importlib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from camzyos import engine, inspection, library, reranking, retrieval


@pytest.fixture
def pdf_library(cfg, monkeypatch):
    cfg.update(retrieval_scope="all_documents", api_key="test-placeholder", retrieval_top_k=8)
    specs = [("eu_smpc", "EU", "label"), ("de_fachinformation", "DE", "label"),
             ("eu_rmp", "EU", "risk_management"), ("eu_overview", "EU", "overview"),
             ("eu_changes", "EU", "history"), ("eu_changes_archive", "EU", "history"),
             ("us_fda", "US", "label"), ("us_bms", "US", "label")]
    documents = []
    for sid, market, kind in specs:
        source = {"id": sid, "title": sid, "market": market, "kind": kind, "audience": "public" if sid == "eu_overview" else "HCP",
                  "eligible": sid in {"eu_smpc", "de_fachinformation"}}
        passage = {"id": f"inspection:{sid}:v1:p1:0", "version_id": f"inspection:{sid}:v1",
                   "text": f"Document {sid} contains a synthetic library fact.", "source": source,
                   "page": 1, "page_end": 1, "corpus": "inspection", "clinical_evidence": False,
                   "requires_review": True}
        documents.append({"source_id": sid, "source": source, "chunks": [passage], "checksum": sid})
    monkeypatch.setattr(library, "sources", lambda cfg: [d["source"] for d in documents])
    monkeypatch.setattr(inspection, "load", lambda *args: copy.deepcopy(documents))
    monkeypatch.setattr(inspection, "index_status", lambda cfg, chunks: {"ready": True})
    monkeypatch.setattr(inspection, "report", lambda *args: {
        "ready": True, "expected_chunks": 8, "indexed_chunks": 8, "document_count": 8,
        "index_state": "ONLINE", "missing_ids": [], "errors": []})
    monkeypatch.setattr(inspection, "_vector_search", lambda cfg, question, chunks: [c["id"] for c in chunks])
    return documents


def test_all_eight_stay_indexed_but_only_eligible_sources_enter_chat(cfg, store, pdf_library, monkeypatch):
    monkeypatch.setattr(store, "chunks", lambda *args: pytest.fail("Library retrieval must not use the 20-chunk gate"))
    passages, backend, warnings = retrieval.retrieve(cfg, store, "synthetic library fact")
    assert {p["source"]["id"] for p in passages} == {"eu_smpc", "de_fachinformation"}
    assert len(passages) == 2 and "All-PDF" in backend and not warnings
    assert all(p["clinical_evidence"] is False and p["requires_review"] for p in passages)


def test_private_documents_do_not_cross_hcp_accounts(cfg, store, pdf_library):
    pdf_library[1]["chunks"][0]["source"]["account_id"] = "account_A"
    for account, expected in [(None, 1), ("account_B", 1), ("account_A", 2)]:
        passages, _, _ = retrieval.retrieve(cfg, store, "library fact", account)
        assert len(passages) == expected
    assert library.status(cfg, "account_B")["document_count"] == 8
    assert library.status(cfg, "account_B")["eligible_document_count"] == 1


def test_reranking_cannot_rewrite_or_reassign_library_evidence(cfg, store, pdf_library, monkeypatch):
    cfg["reranking_enabled"] = True
    def tamper(cfg, query, passages):
        passages[0]["source"]["market"] = "invented-market"
        return passages
    monkeypatch.setattr(library, "rerank", tamper)
    with pytest.raises(retrieval.RetrievalNotReady):
        retrieval.retrieve(cfg, store, "library fact")


def test_library_reranker_sees_market_and_preserves_original_ids(cfg, pdf_library, monkeypatch):
    passages = [d["chunks"][0] for d in pdf_library]
    def rank(cfg, schema, instruction, payload, **kwargs):
        assert {row["market"] for row in payload["passages"]} == {"EU", "DE", "US"}
        assert all(row["requires_review"] for row in payload["passages"])
        return schema.model_validate({row["slot"]: {"relevance": 2, "reason": "Fixture"}
                                      for row in payload["passages"]})
    monkeypatch.setattr(reranking, "structured", rank)
    ranked = reranking.rerank(cfg, "library fact", passages)
    assert [p["id"] for p in ranked] == [p["id"] for p in passages]
    assert all(p["clinical_evidence"] is False for p in ranked)


def test_library_outage_blocks_chat_before_any_model_call(cfg, store, tables, pdf_library, monkeypatch):
    monkeypatch.setattr(inspection, "report", lambda *args: {
        "ready": False, "expected_chunks": 8, "indexed_chunks": 7, "index_state": "incomplete"})
    monkeypatch.setattr(engine, "parse", lambda *args: pytest.fail("No generation with an incomplete library"))
    result = engine.ask(cfg, store, tables, "a@example.test", "Explain the risk management plan")
    assert result["decision"] == "setup" and "7/8" in result["answer"]


def test_missing_manifest_never_falls_back_to_clinical_subset(cfg, store, pdf_library, monkeypatch):
    def missing(*args):
        raise FileNotFoundError("fixture")
    monkeypatch.setattr(inspection, "load", missing)
    assert not retrieval.status(cfg, store)["ready"]
    with pytest.raises(retrieval.RetrievalNotReady):
        retrieval.retrieve(cfg, store, "library fact")


@pytest.mark.parametrize("source_index", range(8))
def test_each_pdf_can_support_chat_only_when_approved_and_matching_scope(
        cfg, store, tables, pdf_library, source_index, monkeypatch, indexed):
    selected = pdf_library[source_index]["chunks"][0]
    # Synthetic approval: no real registry or bundled document is promoted by this test.
    selected["source"].update(eligible=True, audience="HCP")
    cfg["market"] = "US" if selected["source"]["market"] == "US" else "DE"
    def parse(cfg, schema, instruction, payload):
        assert payload["DOCUMENT_SCOPE"] == "all_documents"
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Document question", topic="general",
                                   retrieval_query="synthetic library fact")
        if schema is engine.Answer:
            return engine.answer_schema(payload).model_validate({
                "introduction": "", "context_used": [], "limitations": [], "insufficient": False,
                "claims": [{"text": selected["text"], "evidence_ids": [selected["id"]]}]})
        assert payload["claims"][0]["cited_evidence"][0]["source"] == selected["source"]
        return engine.Verification(answers_question=True, response_preferences_followed=True, all_claims_supported=True, personal_context_supported=True,
                                   within_scope=True, reason="Synthetic source-attributed fact")
    monkeypatch.setattr(engine, "parse", parse)
    result = engine.ask(cfg, store, tables, "a@example.test", "Summarize this document's contents")
    assert result["decision"] == "answer"
    assert [{k: v for k, v in p.items() if k != "retrieval"} for p in result["citations"]] == [selected]
    assert result["document_scope"] == "all_documents"
    assert all(p["source"]["eligible"] for p in result["retrieved_evidence"])
    assert len(result["retrieved_evidence"]) == len(library.chunks(cfg))
    assert store.history("HCP_A") == []


def test_page_shows_full_corpus_and_enables_chat(cfg, store, tables, pdf_library, monkeypatch):
    settings_module = importlib.import_module("camzyos.settings")
    monkeypatch.setattr(settings_module, "settings", lambda: cfg)
    monkeypatch.setattr(engine.profiles, "load_profiles", lambda path: tables)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception and not app.chat_input[0].disabled
    assert any("8 PDFs" in message.value for message in app.success)


@pytest.mark.parametrize("changes", [
    {"eligible": False}, {"valid_to": "2000-01-01"}, {"audience": "public"}, {"market": "US"},
    {"status": "withdrawn"}, {"approved": False},
])
def test_source_filters_apply_before_vector_search(cfg, store, pdf_library, monkeypatch, changes):
    rejected = pdf_library[0]["chunks"][0]
    rejected["source"].update(changes)
    def vector(config, query, candidates):
        assert rejected["id"] not in {p["id"] for p in candidates}
        return [rejected["id"], *[p["id"] for p in candidates]]
    monkeypatch.setattr(inspection, "_vector_search", vector)
    passages, _, _ = retrieval.retrieve(cfg, store, "synthetic library fact")
    assert [p["source"]["id"] for p in passages] == ["de_fachinformation"]


def test_medical_boundary_filters_nonmedical_content_before_search(cfg, store, pdf_library):
    pdf_library[0]["source"]["kind"] = "promotional"
    cfg["medical_only"] = True
    passages, _, _ = retrieval.retrieve(cfg, store, "synthetic library fact")
    assert [p["source"]["id"] for p in passages] == ["de_fachinformation"]


def test_below_threshold_passages_cannot_reach_generation(cfg, store, pdf_library, monkeypatch):
    cfg["reranking_enabled"] = True
    monkeypatch.setattr(library, "rerank", lambda c, q, ps:
        [{**p, "retrieval": {"relevance": 1}} for p in ps])
    passages, _, _ = retrieval.retrieve(cfg, store, "unrelated question")
    assert not passages


def test_expired_sources_are_rechecked_after_reranking(cfg, store, pdf_library, monkeypatch):
    cfg["reranking_enabled"] = True
    def expire(config, query, passages):
        pdf_library[0]["source"]["valid_to"] = "2000-01-01"
        return [{**p, "retrieval": {"relevance": 3}} for p in passages]
    monkeypatch.setattr(library, "rerank", expire)
    with pytest.raises(retrieval.RetrievalNotReady):
        retrieval.retrieve(cfg, store, "synthetic library fact")
