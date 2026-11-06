"""Recorded preferences shape presentation without truncation or bypassing evidence checks."""
import copy

import pytest

from camzyos import engine, presentation, profiles


def answer(*texts):
    return engine.Answer(introduction="", context_used=[], limitations=[], insufficient=False,
                         claims=[engine.Claim(text=text, evidence_ids=["v1:0"]) for text in texts])


def test_prakash_workbook_preferences_become_a_concise_plan(cfg):
    tables = profiles.load_profiles(cfg["workbook"])
    hcp = profiles.resolve_hcp(tables, "prakash.prakash@zs.com")
    style = presentation.plan(engine.context_items(tables, hcp))
    assert style["detail"] == "brief" and style["layout"] == "bullets"
    assert style["preference_context_ids"] == [hcp["hcp_id"] + ".communicationStyle"]
    assert "Two sites, ten minutes" in str(style["preferences"])
    assert "HCP_DE_000" not in str(style)  # Anna's profile is not included.


def test_plan_uses_preference_text_instead_of_a_specific_name_or_id():
    style = presentation.plan({"ANY_HCP.communicationStyle": "Short and concrete", "memory.fake": "Long prose"})
    assert style["detail"] == "brief"
    assert style["preference_context_ids"] == ["ANY_HCP.communicationStyle"]
    assert "memory.fake" not in style["preferences"]


def test_explicit_detailed_paragraphs_override_short_profile():
    style = presentation.plan({"HCP_A.communicationStyle": "Short and concrete"}, "detailed", "paragraphs")
    assert not any(key.startswith("max_") for key in style)
    assert style["layout"] == "paragraphs" and style["preference_context_ids"] == []
    assert presentation.check(answer("Long " * 100), style)["passed"]


def test_unknown_hcp_has_no_personality_defaults():
    style = presentation.plan({})
    assert style["preferences"] == {} and style["preference_context_ids"] == []
    assert "max_words" not in style


def test_answer_length_is_measured_but_never_restricted():
    style = presentation.plan({"HCP_A.communicationStyle": "Concise"})
    draft = answer(*["word " * 120 for _ in range(8)])
    draft.limitations = ["qualification " * 200]
    check = presentation.check(draft, style)
    assert check["word_count"] == 1160 and check["claim_count"] == 8
    assert check["passed"] and not check["issues"]
    assert "max_words" not in style


@pytest.mark.parametrize("layout,prefix", [("bullets", "- "), ("numbered", "1. "), ("paragraphs", "")])
def test_renderer_preserves_every_verified_word_and_citation(layout, prefix):
    original = answer("A qualification must remain even if it is long. " * 12, "Another supported point.")
    before = original.model_dump()
    style = presentation.plan({"HCP_A.communicationStyle": "Concise"}, detail="detailed", layout=layout)
    rendered = presentation.render(original, ["v1:0"], style)
    assert rendered.startswith(prefix + original.claims[0].text)
    assert all(claim.text + " [1]" in rendered for claim in original.claims)
    assert original.model_dump() == before


@pytest.mark.parametrize("valid_revision", [True, False])
def test_personality_feedback_revises_once_and_every_revision_is_evidence_checked(
        cfg, store, tables, indexed, monkeypatch, valid_revision):
    cfg["api_key"] = "test-placeholder"
    generated, audited = [], []
    def parse(config, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Test", topic="general", retrieval_query="monitoring")
        if schema is engine.Answer:
            generated.append(copy.deepcopy(payload))
            assert payload["RESPONSE_STYLE"]["detail"] == "brief"
            if len(generated) == 1:
                return answer("Unnecessary generic background.")
            assert "Use focused points for this HCP." in payload["REVISION"]["reason"]
            assert payload["EVIDENCE"] == generated[0]["EVIDENCE"]
            return answer("A concise synthetic fact.", "A separate qualification.")
        return engine.Verification(answers_question=True, response_preferences_followed=len(generated) > 1,
            all_claims_supported=True, personal_context_supported=True, within_scope=True,
            reason="Use focused points for this HCP.")
    def audit(config, claims, evidence):
        audited.append([claim.text for claim in claims])
        passed = len(audited) == 1 or valid_revision
        return {"passed": passed, "claims": [], "issues": [] if passed else ["Unsupported rewrite"]}
    monkeypatch.setattr(engine, "parse", parse)
    monkeypatch.setattr(engine.grounding, "audit", audit)
    monkeypatch.setattr(presentation, "review", lambda *args: {
        "passed": len(generated) > 1, "issues": [] if len(generated) > 1 else ["Use focused points for this HCP."]})
    result = engine.ask(cfg, store, tables, "a@example.test", "What is the synthetic product?")
    assert len(generated) == 2 and len(audited) == 2
    if valid_revision:
        assert result["decision"] == "answer"
        assert result["answer"] == "- A concise synthetic fact. [1]\n\n- A separate qualification. [1]"
        assert result["context_used"] == {"HCP_A.communicationStyle": "Concise"}
        assert result["presentation_gate"]["preference_review_passed"]
    else:
        assert result["decision"] == "handoff" and result["rule_ids"] == ["GR_15"]
        assert "A concise synthetic fact" not in result["answer"]


def test_missing_personality_review_cannot_release_an_answer(cfg, store, tables, indexed, monkeypatch):
    cfg["api_key"] = "test-placeholder"
    def parse(config, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Test", topic="general", retrieval_query="monitoring")
        if schema is engine.Answer:
            return answer("A source-supported fact.")
        return engine.Verification(answers_question=True, all_claims_supported=True, personal_context_supported=True,
                                   within_scope=True, reason="No personality assessment supplied")
    monkeypatch.setattr(engine, "parse", parse)
    monkeypatch.setattr(presentation, "review", lambda *args: {"passed": False, "issues": ["Review unavailable"]})
    result = engine.ask(cfg, store, tables, "a@example.test", "What is this?")
    assert result["decision"] == "clarify" and result["rule_ids"] == ["GR_15"]
    assert not result["citations"] and "source-supported fact" not in result["answer"]


def test_independent_review_catches_missing_requested_topic(cfg, monkeypatch):
    def structured(config, schema, instruction, payload, **kwargs):
        assert payload["question"] == "Explain approved use and safety"
        return schema(followed=True, question_addressed=False, issues=["The requested approved use is missing."])
    monkeypatch.setattr(presentation, "structured", structured)
    result = presentation.review(cfg, "Explain approved use and safety", answer("Safety only."), presentation.plan({}))
    assert not result["question_addressed"] and not result["passed"]


def test_explicit_language_is_resolved_without_conflicting_language_defaults():
    plan = presentation.plan({"HCP_A.language": "German", "HCP_A.communicationStyle": "Short and concrete"},
                             detail="detailed", language="English")
    assert plan["language"] == "English" and plan["language_source"] == "explicit_user_request"
    assert "HCP_A.language" not in plan["preferences"] and plan["detail"] == "detailed"


def test_risk_first_profile_orders_whole_claims_before_verification_without_word_limits():
    draft = answer("The approved use with its qualifiers.", "A relevant risk and its qualifications.")
    draft.claims[0].category = "identity_use"
    draft.claims[1].category = "safety"
    original = draft.model_dump()
    style = presentation.plan({"HCP_A.communicationStyle": "Careful; asks about risks first and needs time"})
    ordered = presentation.arrange(draft, style)
    assert ordered.claims == [draft.claims[1], draft.claims[0]]
    assert draft.model_dump() == original and style["preference_context_ids"] == ["HCP_A.communicationStyle"]
    explicit = presentation.plan({"HCP_A.communicationStyle": "Risks first"}, order="use_first")
    assert presentation.arrange(ordered, explicit).claims == draft.claims


def test_risk_first_profile_does_not_invent_risks_for_a_definition():
    draft = answer("A medicine and its authorised use.")
    draft.claims[0].category = "identity_use"
    assert presentation.arrange(draft, presentation.plan({"HCP_A.communicationStyle": "Risks first"})).claims == draft.claims


def test_detailed_user_request_gets_no_brevity_rewrite(cfg, store, tables, indexed, monkeypatch):
    cfg["api_key"] = "test-placeholder"
    calls = []
    def parse(config, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Test", topic="general", retrieval_query="monitoring",
                                   requested_detail="detailed", requested_format="paragraphs")
        if schema is engine.Answer:
            calls.append(payload)
            assert payload["RESPONSE_STYLE"]["detail"] == "detailed"
            assert "STYLE_REVISION" not in payload
            return answer("Detailed synthetic explanation. " * 40)
        return engine.Verification(answers_question=True, response_preferences_followed=True, all_claims_supported=True, personal_context_supported=True,
                                   within_scope=True, reason="Fixture")
    monkeypatch.setattr(engine, "parse", parse)
    result = engine.ask(cfg, store, tables, "a@example.test", "Explain in detail using paragraphs.")
    assert result["decision"] == "answer" and len(calls) == 1
    assert "max_words" not in result["response_style"]
    assert result["context_used"] == {}


def test_document_only_mode_does_not_inherit_hcp_style(cfg, store, tables, indexed, monkeypatch):
    cfg["api_key"] = "test-placeholder"
    def parse(config, schema, instruction, payload):
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Test", topic="general", retrieval_query="monitoring")
        if schema is engine.Answer:
            assert payload["CONTEXT"] == {}
            assert payload["RESPONSE_STYLE"]["preferences"] == {}
            return answer("A synthetic fact.")
        return engine.Verification(answers_question=True, response_preferences_followed=True, all_claims_supported=True, personal_context_supported=True,
                                   within_scope=True, reason="Fixture")
    monkeypatch.setattr(engine, "parse", parse)
    result = engine.ask(cfg, store, tables, "a@example.test", "What is the synthetic product?", mode="documents")
    assert result["decision"] == "answer" and "max_words" not in result["response_style"]
