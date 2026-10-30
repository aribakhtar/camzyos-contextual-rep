from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from camzyos import engine


def candidate():
    return {"introduction": "Dr. Alpha, here is the requested information.",
            "context_used": ["HCP_A.name"],
            "claims": [{"text": "Synthetic test fact.", "evidence_ids": ["v1:0"]}],
            "limitations": [], "insufficient": False}


@pytest.mark.parametrize("invalid_field", ["context", "evidence"])
def test_model_schema_prevents_swapping_document_and_hcp_ids(invalid_field):
    schema = engine.answer_schema({"EVIDENCE": [{"id": "v1:0"}], "CONTEXT": {"HCP_A.name": "Dr. Alpha"}})
    data = candidate()
    assert schema.model_validate(data).context_used == ["HCP_A.name"]
    if invalid_field == "context":
        data["context_used"] = ["v1:0"]  # Reproduced live failure: a source ID was used as personal context.
    else:
        data["claims"][0]["evidence_ids"] = ["HCP_A.name"]
    with pytest.raises(ValidationError):
        schema.model_validate(data)


def test_unknown_hcp_schema_allows_only_empty_context():
    schema = engine.answer_schema({"EVIDENCE": [{"id": "v1:0"}], "CONTEXT": {}})
    data = candidate()
    with pytest.raises(ValidationError):
        schema.model_validate(data)
    data.update(introduction="", context_used=[])
    assert schema.model_validate(data).context_used == []
    data.update(insufficient=True, claims=[])
    assert schema.model_validate(data).insufficient  # Genuine evidence gaps still permit abstention.


def test_parse_supplies_scoped_schema_to_provider(cfg, monkeypatch):
    def parse(**kwargs):
        schema = kwargs["text_format"]
        data = candidate()
        data["context_used"] = ["v1:0"]
        with pytest.raises(ValidationError):
            schema.model_validate(data)
        return SimpleNamespace(output_parsed=schema.model_validate(candidate()))
    monkeypatch.setattr(engine, "OpenAI", lambda **kw: SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    result = engine.parse(cfg, engine.Answer, "Test only", {
        "EVIDENCE": [{"id": "v1:0"}], "CONTEXT": {"HCP_A.name": "Dr. Alpha"}})
    assert isinstance(result, engine.Answer)


@pytest.mark.parametrize("failure", ["invalid_ids", "verification", "insufficient"])
def test_refusal_distinguishes_validation_from_missing_evidence(cfg, store, tables, monkeypatch, failure, indexed):
    cfg["api_key"] = "test-placeholder"

    def parse(cfg, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Test", topic="general",
                                   retrieval_query="monitoring information")
        if schema is engine.Answer:
            data = candidate()
            if failure == "invalid_ids":
                data["context_used"] = ["v1:0"]
            data["insufficient"] = failure == "insufficient"
            return engine.Answer(**data)
        return engine.Verification(all_claims_supported=False, personal_context_supported=True,
                                   within_scope=True, reason="Unsupported test claim")
    monkeypatch.setattr(engine, "parse", parse)
    result = engine.ask(cfg, store, tables, "a@example.test", "monitoring information")
    assert result["decision"] == "handoff"
    assert result["answer"] == engine.REASONS["insufficient" if failure == "insufficient" else "validation"]
    assert "Synthetic test fact" not in str(result)


def test_verifier_receives_only_each_claims_cited_passages_and_selected_context():
    answer = engine.Answer(**candidate())
    evidence = [{"id": "v1:0", "text": "Unrelated passage."},
                {"id": "v1:1", "text": "Synthetic test fact."}]
    payload = engine.verification_payload("Test question", answer, evidence,
                                          {"HCP_A.name": "Dr. Alpha", "HCP_A.workplace": "Hospital"})
    assert payload["claims"][0]["cited_evidence"] == [evidence[0]]
    assert "v1:1" not in str(payload)
    assert payload["PERSONAL_CONTEXT"] == {"HCP_A.name": "Dr. Alpha"}
    assert payload["personal_assertions_to_verify"] == [answer.introduction]


def test_silent_style_preference_keeps_context_trace_and_citations(cfg, store, tables, monkeypatch, indexed):
    cfg["api_key"] = "test-placeholder"

    def parse(cfg, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Test", topic="general",
                                   retrieval_query="monitoring information")
        if schema is engine.Answer:
            data = candidate()
            data.update(introduction="", context_used=["HCP_A.communicationStyle"])
            return engine.answer_schema(payload).model_validate(data)
        assert payload["introduction"] == ""
        assert payload["personal_assertions_to_verify"] == []
        assert payload["PERSONAL_CONTEXT"] == {"HCP_A.communicationStyle": "Concise"}
        assert payload["claims"][0]["cited_evidence"][0]["id"] == "v1:0"
        return engine.Verification(all_claims_supported=True, personal_context_supported=True,
                                   within_scope=True, reason="Test verification")

    monkeypatch.setattr(engine, "parse", parse)
    result = engine.ask(cfg, store, tables, "a@example.test", "monitoring information")
    assert result["decision"] == "answer"
    assert result["answer"] == "Synthetic test fact. [1]"
    assert result["context_used"] == {"HCP_A.communicationStyle": "Concise"}
    assert [citation["id"] for citation in result["citations"]] == ["v1:0"]
    assert "HCP_B" not in str(result)
    assert store.history("HCP_A") == []


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_one_correction_is_reverified_before_display(cfg, store, tables, monkeypatch, repair_succeeds, indexed):
    cfg["api_key"] = "test-placeholder"
    calls = {"answer": 0, "verification": 0}

    def parse(cfg, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Test", topic="general",
                                   retrieval_query="monitoring information")
        if schema is engine.Answer:
            calls["answer"] += 1
            if calls["answer"] == 2:
                assert payload["REVISION"]["reason"] == "Fix the unsupported claim."
            return engine.Answer(**candidate())
        calls["verification"] += 1
        return engine.Verification(all_claims_supported=repair_succeeds and calls["verification"] == 2,
                                   personal_context_supported=True, within_scope=True,
                                   reason="Fix the unsupported claim.")
    monkeypatch.setattr(engine, "parse", parse)
    result = engine.ask(cfg, store, tables, "a@example.test", "monitoring information")
    assert calls == {"answer": 2, "verification": 2}
    assert result["decision"] == ("answer" if repair_succeeds else "handoff")
    assert len(result["verification_checks"]) == 2
    assert result["verification_checks"][0]["all_claims_supported"] is False
    assert result["verification_checks"][0]["reason"] == "Fix the unsupported claim."
    assert result["verification_checks"][1]["all_claims_supported"] is repair_succeeds
    assert store.history("HCP_A") == []


def test_personal_audit_failure_cannot_be_overridden_by_final_verifier(cfg, store, tables, monkeypatch, indexed):
    from camzyos import grounding

    cfg["api_key"] = "test-placeholder"
    def parse(cfg, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Test", topic="general", retrieval_query="monitoring")
        if schema is engine.Answer:
            return engine.Answer(**candidate())
        return engine.Verification(all_claims_supported=True, personal_context_supported=True,
                                   within_scope=True, reason="Test false positive")
    monkeypatch.setattr(engine, "parse", parse)
    monkeypatch.setattr(grounding, "audit_personal", lambda *a: {"passed": False, "reason": "Unsupported personal fact"})
    result = engine.ask(cfg, store, tables, "a@example.test", "monitoring information")
    assert result["decision"] == "handoff" and result["policy_route"] == "validation"
    assert len(result["verification_checks"]) == 2
    assert all(not check["personal_context_supported"] for check in result["verification_checks"])
    assert all(not check["personal_audit"]["passed"] for check in result["verification_checks"])
