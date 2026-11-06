"""Behavior of the user's GR_01–GR_16 contract, including durable routing and false positives."""
from datetime import datetime, timedelta

import pytest

from camzyos import engine, graph, guardrails, profiles, retrieval


@pytest.mark.parametrize("question,rule,target", [
    ("Can CAMZYOS be used for non-obstructive HCM?", "GR_01", "Medical Information"),
    ("A patient developed dizziness after starting CAMZYOS.", "GR_02", "Pharmacovigilance"),
    ("I received damaged capsules.", "GR_03", "Quality"),
    ("What dose should I give my patient?", "GR_04", "MSL"),
    ("Is CAMZYOS better than another medicine?", "GR_05", "MSL"),
    ("Please speak to a human.", "GR_14", "Rep or MSL"),
])
def test_early_escalations_skip_generation_and_log_correct_target(cfg, store, tables, monkeypatch, question, rule, target):
    monkeypatch.setattr(engine, "parse", lambda *args: pytest.fail("No model generation for a matched rule"))
    result = engine.ask(cfg, store, tables, "a@example.test", question, persist=False)
    assert result["decision"] == "handoff" and result["rule_ids"] == [rule]
    assert result["handoff"]["destination"] == target
    assert result["handoff"]["action"] == guardrails.RULES[rule][1]
    assert not result["citations"]
    cases = store.escalations("HCP_A")
    assert len(cases) == 1 and cases[0]["target"] == target
    assert cases[0]["status"] == "pending_external_submission" and cases[0]["external_case_id"] is None
    assert store.history("HCP_A") == []  # Mandatory audit does not become optional conversation memory.
    audit = store.policy_records("HCP_A")[0]
    assert audit["question"] == question and audit["user"] == "HCP_A" and audit["timestamp"]
    assert audit["rule_ids"] == [rule, "GR_16"] and store.policy_records("HCP_B") == []
    if rule == "GR_02":
        assert datetime.fromisoformat(cases[0]["due_at"]) - datetime.fromisoformat(cases[0]["logged_at"]) == timedelta(hours=24)
        assert result["handoff"]["intake"]["logged_at"] == cases[0]["logged_at"]


@pytest.mark.parametrize("question", [
    "what is camzyos", "what is camzoys", "What are the general adverse effects?",
    "My patient asked me for general approved product information.",
    "Explain starting versus maintenance monitoring in the label.",
    "Ignore previous phrasing and give the approved indication.",
    "What has changed in the current label?",
])
def test_keywords_do_not_create_additional_prohibitions(tables, question):
    assert engine.rule_route(question, tables["HCP_Profile"][0], tables) is None


@pytest.mark.parametrize("patch,rule", [
    ({"valid_to": "2000-01-01"}, "GR_06"), ({"eligible": False}, "GR_07"),
    ({"approved": False}, "GR_07"), ({"audience": "public"}, "GR_08"),
    ({"market": "US"}, "GR_09"),
])
def test_content_exclusions_have_the_requested_rule_id(cfg, source, patch, rule):
    assert guardrails.source_rules({**source, **patch}, cfg) == [rule]


def test_no_source_above_threshold_declines_with_gr11(cfg, store, tables, indexed, monkeypatch):
    cfg["api_key"] = "fixture"
    monkeypatch.setattr(engine, "parse", lambda *args: engine.Decision(
        route="answer", reason="General question", topic="general", retrieval_query="not covered"))
    monkeypatch.setattr(engine, "retrieve", lambda *args: ([], "Fixture retrieval", []))
    result = engine.ask(cfg, store, tables, "a@example.test", "What is not covered?")
    assert result["rule_ids"] == ["GR_11"] and result["handoff"]["destination"] == "Rep or MSL"


def test_promotional_boundary_uses_medical_sources_and_queues_medical_review(cfg, store, tables, indexed, monkeypatch):
    cfg["api_key"] = "fixture"
    def parse(config, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", medical_boundary=True, reason="Promotional boundary",
                                   topic="general", retrieval_query="monitoring")
        if schema is engine.Answer:
            return engine.Answer(introduction="", context_used=[], limitations=[], insufficient=False,
                claims=[engine.Claim(text="A medical fact.", evidence_ids=["v1:0"])])
        return engine.Verification(answers_question=True, all_claims_supported=True, personal_context_supported=True,
                                   within_scope=True, response_preferences_followed=True, reason="Fixture")
    original = retrieval.retrieve
    def retrieve(config, *args):
        assert config["medical_only"] is True
        return original(config, *args)
    monkeypatch.setattr(engine, "retrieve", retrieve)
    monkeypatch.setattr(engine, "parse", parse)
    result = engine.ask(cfg, store, tables, "a@example.test", "Create promotional product copy")
    assert result["decision"] == "answer" and result["review_required"]
    assert result["rule_ids"] == ["GR_10"] and result["review_target"] == "Medical"
    assert store.escalations("HCP_A")[0]["target"] == "Medical"


def test_proactive_message_without_consent_is_suppressed_before_model(cfg, store, tables, monkeypatch):
    monkeypatch.setattr(engine, "parse", lambda *args: pytest.fail("No unconsented proactive generation"))
    result = engine.ask(cfg, store, tables, "a@example.test", "An unsolicited update", proactive=True)
    assert result["decision"] == "suppressed" and result["rule_ids"] == ["GR_12"]
    assert result["answer"] == "" and not result["citations"]
    assert store.policy_records("HCP_A")[0]["rule_ids"] == ["GR_12", "GR_16"]


def test_workbook_outbound_consent_is_recognized(cfg):
    tables = profiles.load_profiles(cfg["workbook"])
    assert guardrails.outbound_consent(tables["HCP_Profile"][0])
    assert not guardrails.outbound_consent({"proactive_outbound_consent": "No"})


@pytest.mark.parametrize("question", [
    "What should I know about the approved use and important safety information for CAMZYOS?",
    "I do not want promotional copy. Explain the approved indication.",
])
def test_plain_medical_information_has_no_promotional_signal(question):
    from camzyos import policy
    assert not policy.promotional_signal(question)


def test_confidential_records_never_enter_context_or_graph_signal_layer(tables, monkeypatch):
    tables["Personality"].append({"hcp_id": "HCP_A", "confidential": True, "notes": "Hidden personality"})
    tables["HCP_Interactions"].append({"hcp_id": "HCP_A", "notes": "Confidential business insight"})
    loaded = profiles.context(tables, tables["HCP_Profile"][0])
    assert "Hidden personality" not in str(loaded) and "Confidential business insight" not in str(loaded)
    monkeypatch.setattr(graph, "memory_client", lambda *args: pytest.fail("No confidential graph writes"))
    assert graph.retain({}, "HCP_A", {"hcp_said": "Confidential business insight"}, consent=True) is None


def test_unavailable_confidence_review_escalates_to_rep_or_msl(cfg, store, tables, indexed, monkeypatch):
    cfg["api_key"] = "fixture"
    monkeypatch.setattr(engine, "parse", lambda *args: engine.Decision(
        route="answer", reason="General question", topic="general", retrieval_query="monitoring"))
    def unavailable(*args):
        raise retrieval.RetrievalConfidenceUnavailable("Fixture scorer unavailable")
    monkeypatch.setattr(engine, "retrieve", unavailable)
    result = engine.ask(cfg, store, tables, "a@example.test", "Explain monitoring")
    assert result["rule_ids"] == ["GR_15"] and result["handoff"]["destination"] == "Rep or MSL"


def test_audit_failure_does_not_claim_an_intake_was_saved(cfg, store, tables, monkeypatch):
    def unavailable(*args):
        raise OSError("Storage unavailable")
    monkeypatch.setattr(store, "record_policy", unavailable)
    result = engine.ask(cfg, store, tables, "a@example.test", "I received damaged capsules")
    assert result["decision"] == "error" and result["rule_ids"] == ["GR_16"]
    assert result["handoff"] is None and not store.escalations("HCP_A")


def test_rules_are_exactly_the_user_supplied_sixteen():
    assert set(guardrails.RULES) == {f"GR_{index:02d}" for index in range(1, 17)}


def test_failed_intake_rolls_back_its_audit_in_the_same_transaction(cfg, store, tables):
    with store.db() as db:
        db.execute("CREATE TRIGGER fail_intake BEFORE INSERT ON escalation_cases "
                   "BEGIN SELECT RAISE(ABORT, 'Fixture intake unavailable'); END")
    result = engine.ask(cfg, store, tables, "a@example.test", "I received damaged capsules")
    assert result["decision"] == "error" and result["rule_ids"] == ["GR_16"]
    assert not store.escalations("HCP_A") and not store.policy_records("HCP_A")


def test_relevance_threshold_also_applies_without_reranking(cfg):
    passages = [{"id": "matched", "retrieval": {"keyword_matches": 2}},
                {"id": "unrelated", "retrieval": {"keyword_matches": 0}}]
    assert [p["id"] for p in guardrails.above_threshold(cfg, passages)] == ["matched"]


@pytest.mark.parametrize("complete", [True, False])
def test_only_proven_claims_can_be_retained_and_incomplete_subset_is_not_released(
        cfg, store, tables, indexed, monkeypatch, complete):
    cfg["api_key"] = "fixture"
    drafts = []
    def parse(config, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Test", topic="general", retrieval_query="monitoring")
        if schema is engine.Answer:
            drafts.append(payload)
            return engine.Answer(introduction="", context_used=[], limitations=[], insufficient=False,
                claims=[engine.Claim(text="An independently proven fact.", evidence_ids=["v1:0"]),
                        engine.Claim(text="An unsupported extra claim.", evidence_ids=["v1:0"])])
        assert [c["text"] for c in payload["claims"]] == ["An independently proven fact."]
        return engine.Verification(answers_question=complete, all_claims_supported=True,
            personal_context_supported=True, within_scope=True, response_preferences_followed=False,
            reason="Complete" if complete else "Missing a requested safety component")
    def audit(config, claims, evidence):
        return {"passed": False, "issues": ["Unsupported addition"], "claims": [
            {"claim_index": i, "text": c.text, "passed": i == 0, "issues": [] if i == 0 else ["Unsupported addition"]}
            for i, c in enumerate(claims)]}
    monkeypatch.setattr(engine, "parse", parse)
    monkeypatch.setattr(engine.grounding, "audit", audit)
    result = engine.ask(cfg, store, tables, "a@example.test", "What is the supported information?")
    assert len(drafts) == 2 and "An unsupported extra claim." not in result["answer"]
    if complete:
        assert result["decision"] == "answer" and "An independently proven fact." in result["answer"]
        assert result["grounding_audits"][-1]["unchanged_supported_subset"]
    else:
        assert result["decision"] == "handoff" and result["rule_ids"] == ["GR_15"]
        assert "An independently proven fact." not in result["answer"] and not result["citations"]


def test_multipart_retrieval_keeps_evidence_for_each_requested_topic(cfg, store, source, tables, indexed, monkeypatch):
    from pathlib import Path
    cfg.update(api_key="fixture", retrieval_top_k=4)
    store.stage(source, "topics", "new", [{"text": f"Topic fact {i}", "page": 1} for i in range(6)], [], Path("fixture.pdf"))
    store.activate("topics", "Synthetic multifacet test")
    chunks = store.chunks()
    requested = []
    def retrieve(config, db, query, account):
        requested.append(query)
        return (chunks[:3] if query == "approved use" else chunks[3:]), "Fixture", []
    def parse(config, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Two parts", topic="general",
                retrieval_query="approved use and safety", retrieval_queries=["approved use", "safety"])
        if schema is engine.Answer:
            assert payload["REQUESTED_TOPICS"] == ["approved use", "safety"]
            assert [p["id"] for p in payload["EVIDENCE"]] == ["topics:0", "topics:3", "topics:1", "topics:4"]
            return engine.Answer(introduction="", context_used=[], limitations=[], insufficient=False,
                claims=[engine.Claim(text="The use and safety facts.", evidence_ids=["topics:0", "topics:3"])])
        assert payload["REQUESTED_TOPICS"] == ["approved use", "safety"]
        return engine.Verification(answers_question=True, all_claims_supported=True,
            personal_context_supported=True, within_scope=True, reason="Fixture")
    monkeypatch.setattr(engine, "retrieve", retrieve)
    monkeypatch.setattr(engine, "parse", parse)
    result = engine.ask(cfg, store, tables, "a@example.test", "Explain the approved use and safety")
    assert result["decision"] == "answer" and requested == ["approved use", "safety"]
    assert result["retrieval_queries"] == requested
