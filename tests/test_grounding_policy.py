import copy

import pytest

from camzyos import engine, grounding, policy

EVENTS = [
    "A patient at our hospital became breathless and developed leg swelling after starting. Is that expected?",
    "A patient fainted three weeks after a dose increase. Is that known with this drug?",
    "One of my registrars told me a patient developed leg oedema and breathlessness six weeks after starting. What do we do?",
    "A colleague's patient fainted after starting. Is that known with this drug?",
    "A patient started at the centre and now followed by me has breathlessness and swelling. Is that the drug?",
    "A shared patient reports dizziness and fainting since the dose was raised at the centre.",
    "Mein Patient bekam nach Beginn der Behandlung Schwindel.",
    "My patient has no rash but developed dizziness after starting treatment.",
]


@pytest.mark.parametrize("question", EVENTS)
def test_reported_events_take_priority_without_model_or_retrieval(cfg, store, tables, monkeypatch, question):
    monkeypatch.setattr(engine, "parse", lambda *a: pytest.fail("AE must not reach generation/classification"))
    monkeypatch.setattr(engine, "retrieve", lambda *a: pytest.fail("AE must not retrieve clinical advice"))
    result = engine.ask(cfg, store, tables, "a@example.test", question)
    assert result["policy_route"] == "adverse_event" and result["decision"] == "handoff"
    assert result["handoff"]["destination"] == "Pharmacovigilance"
    assert result["handoff"]["intake"]["status"] == "draft_not_submitted"
    assert result["handoff"]["intake"]["external_case_id"] is None
    assert result["citations"] == [] and store.history("HCP_A") == []


@pytest.mark.parametrize("question", [
    "What are the general adverse effects?", "Can patients develop fainting after starting treatment?",
    "No patient has fainted after treatment. I am asking about the general risk.",
    "My patient has no breathlessness or swelling after starting treatment.",
    "Can CAMZYOS cause dizziness?",
    "Hypothetically, a patient developed dizziness after starting. How would reporting work?",
    "What if a patient developed dizziness after starting?",
])
def test_general_hypothetical_and_negated_symptoms_are_not_reports(question):
    assert not policy.reported_event(question)


def test_pronoun_event_uses_own_conversation_exposure(cfg, store, tables):
    history = [{"role": "user", "content": "My patient started CAMZYOS last week.", "hcp_id": "HCP_A"}]
    result = engine.ask(cfg, store, tables, "a@example.test", "She became breathless today.", history=history)
    assert result["policy_route"] == "adverse_event"
    assert not policy.reported_event("Separately, what are the general adverse effects?", history)


@pytest.mark.parametrize("question", [
    "What has changed since we last spoke in August?", "Tell me what is new, not what I already know.",
    "Anything new since my last email in August? Three lines max.", "Was hat sich seit August geändert?",
])
def test_temporal_plan_resolves_own_context_but_requires_reviewed_comparison(cfg, store, tables, monkeypatch, question):
    tables = copy.deepcopy(tables)
    tables["HCP_Profile"][0]["last_interaction_date"] = "2026-08-12"
    tables["HCP_Profile"][1]["last_interaction_date"] = "2099-01-01"
    monkeypatch.setattr(engine, "parse", lambda *a: pytest.fail("Do not generate unsupported change claims"))
    result = engine.ask(cfg, store, tables, "a@example.test", question)
    assert result["policy_route"] == "unverified_update"
    assert result["context_used"] == {"HCP_A.last_interaction_date": "2026-08-12"}
    assert result["temporal_plan"]["steps"][-1]["status"] == "blocked_without_reviewed_comparison"
    assert "2099" not in str(result) and result["citations"] == []


@pytest.mark.parametrize("question", ["What is the current approved indication?", "How is CAMZYOS administered?"])
def test_current_label_questions_are_not_change_requests(question):
    assert not policy.update_request(question)


@pytest.mark.parametrize("question", [
    "What does the label say about Child-Pugh A or B hepatic impairment?",
    "Please explain Child Pugh classification in the label.",
])
def test_child_pugh_is_not_a_paediatric_use_request(question):
    assert not policy.scope_signal(question)


def test_negated_off_label_text_cannot_be_used_to_justify_an_off_label_refusal(cfg, store, tables, monkeypatch, indexed):
    cfg["api_key"] = "fixture"
    question = "I am not asking about off-label use. What is the approved indication?"
    assert engine.rule_route(question, tables["HCP_Profile"][0], tables) is None
    monkeypatch.setattr(engine, "parse", lambda *a: engine.Decision(route="off_label", reason="Wrong fixture classifier",
        topic="general", retrieval_query="indication", off_label_quote="off-label"))
    result = engine.ask(cfg, store, tables, "a@example.test", question)
    assert result["decision"] == "clarify" and result.get("handoff") is None


def test_unsupported_off_label_classification_does_not_make_false_scope_claim(cfg, store, tables, monkeypatch, indexed):
    cfg["api_key"] = "fixture"
    monkeypatch.setattr(engine, "parse", lambda *a: engine.Decision(route="off_label", reason="Email not supported",
        topic="initiation", retrieval_query="initiation", off_label_quote="checks before a first initiation"))
    result = engine.ask(cfg, store, tables, "a@example.test", "Walk me through the checks before a first initiation.")
    assert result["decision"] == "clarify"
    assert engine.REASONS["off_label"] != result["answer"]


TEXT = ("Renal impairment\nNo dose adjustment to the standard dose and titration scheme is required for patients "
        "with mild to moderate renal impairment.\nHepatic impairment\nThe mavacamten starting dose should be "
        "2.5 mg in all patients with mild and moderate hepatic impairment.\nPaediatric population\nNo data are available.")


def check(subject, quote, verdict="supported"):
    return grounding.AtomicCheck(subject=subject, assertion="Fixture assertion", verdict=verdict,
        supporting_quotes=[grounding.Proof(passage_id="p1", quote=quote)] if verdict == "supported" else [],
        counter_quotes=[], reason="Fixture review")


def test_proof_from_renal_subsection_cannot_support_hepatic_claim():
    quote = "No dose adjustment to the standard dose and titration scheme is required for patients with mild to moderate renal impairment."
    review = grounding.Review(covers_entire_claim=True, checks=[check("renal", quote), check("hepatic", quote)])
    errors = grounding.validate_review(review, "No dose adjustment in mild hepatic or renal impairment.", [{"id":"p1", "text":TEXT}])
    assert any("hepatic population" in e for e in errors)


def test_combined_population_claim_cannot_omit_one_population():
    review = grounding.Review(covers_entire_claim=True, checks=[check("renal", "Renal impairment")])
    assert grounding.validate_review(review, "Bei Leber- oder Nierenfunktionsstörungen ist keine Anpassung nötig.",
                                     [{"id":"p1", "text":TEXT}])


@pytest.mark.parametrize("quote", ["Invented proof text", ""])
def test_proof_must_be_a_real_nonempty_excerpt(quote):
    review = grounding.Review(covers_entire_claim=True, checks=[check("general", quote)])
    assert grounding.validate_review(review, "Fixture", [{"id":"p1", "text":TEXT}])


def test_separate_population_statements_with_matching_excerpts_can_pass():
    renal = "No dose adjustment to the standard dose and titration scheme is required for patients with mild to moderate renal impairment."
    hepatic = "The mavacamten starting dose should be 2.5 mg in all patients with mild and moderate hepatic impairment."
    review = grounding.Review(covers_entire_claim=True, checks=[check("renal", renal), check("hepatic", hepatic)])
    assert not grounding.validate_review(review, "Separate renal and hepatic instructions.", [{"id":"p1", "text":TEXT}])


def test_audit_failure_blocks_answer_even_if_old_verifier_would_pass(cfg, store, tables, monkeypatch, indexed):
    cfg["api_key"] = "fixture"
    calls = []
    def parse(cfg, schema, instruction, payload):
        calls.append(schema)
        if schema is engine.Decision:
            return engine.Decision(route="answer", reason="Fixture", topic="general", retrieval_query="monitoring")
        if schema is engine.Answer:
            return engine.Answer(introduction="", context_used=[], limitations=[], insufficient=False,
                claims=[engine.Claim(text="Unsupported fixture claim", evidence_ids=["v1:0"])])
        pytest.fail("Old verifier must not override failed evidence audit")
    monkeypatch.setattr(engine, "parse", parse)
    monkeypatch.setattr(grounding, "audit", lambda *a: {"passed": False, "claims": [], "issues": ["Contradiction"]})
    result = engine.ask(cfg, store, tables, "a@example.test", "General monitoring information?")
    assert result["policy_route"] == "validation" and calls.count(engine.Answer) == 2
    assert len(result["grounding_audits"]) == 2 and not result["citations"]


def test_current_label_is_not_proof_of_changes_in_generated_text():
    assert policy.novelty_claim("Updated safety information now recommends this.")
    assert not policy.novelty_claim("New or worsening dyspnoea may occur.")
