import pytest
from pydantic import ValidationError

from camzyos import engine, grounding

TEXT = ("Renal impairment\nNo dose adjustment to the standard dose and titration scheme is required for "
        "patients with mild to moderate renal impairment.\nHepatic impairment\nThe mavacamten starting "
        "dose should be 2.5 mg in all patients with mild and moderate hepatic impairment.")


def selected_review(schema, span_id, *, subject="general", verdict="supported", counter=False, covers=True):
    return schema.model_validate({"covers_entire_claim": covers, "checks": [{
        "subject": subject, "assertion": "Test assertion", "verdict": verdict,
        "supporting_quotes": [{"span_id": span_id}] if verdict == "supported" else [],
        "counter_quotes": [{"span_id": span_id}] if counter else [], "reason": "Test audit"}]})


def test_proof_selection_copies_source_bytes_and_never_exposes_uncited_passages(cfg, monkeypatch):
    text = "The supplied\npassage retains its punctuation — and original line breaks."
    evidence = [{"id": "cited", "text": text}, {"id": "uncited", "text": "Unrelated evidence."}]
    claim = engine.Claim(text="Test assertion", evidence_ids=["cited"])

    def structured(cfg, schema, instruction, payload, **kwargs):
        assert [p["id"] for p in payload["cited_evidence"]] == ["cited"]
        assert "Unrelated evidence" not in str(payload)
        spans = payload["cited_evidence"][0]["proof_spans"]
        with pytest.raises(ValidationError):
            selected_review(schema, "unknown-span")
        review = selected_review(schema, spans[0]["span_id"]).model_dump()
        review["checks"][0]["supporting_quotes"] = [{"span_id": span["span_id"]} for span in spans]
        return schema.model_validate(review)

    monkeypatch.setattr(grounding, "structured", structured)
    result = grounding.audit_claim(cfg, claim, evidence, 0)
    assert result["passed"]
    proofs = result["review"]["checks"][0]["supporting_quotes"]
    assert all(proof["passage_id"] == "cited" and proof["quote"] in text for proof in proofs)
    assert "".join(proof["quote"] for proof in proofs) == text
    assert "span_id" in result["proof_selection"]["checks"][0]["supporting_quotes"][0]


@pytest.mark.parametrize("use_correct_population", [False, True])
def test_selected_exact_span_still_requires_the_correct_population(cfg, monkeypatch, use_correct_population):
    claim = engine.Claim(text="The hepatic starting dose is 2.5 mg.", evidence_ids=["p1"])

    def structured(cfg, schema, instruction, payload, **kwargs):
        assert payload["required_subjects"] == ["hepatic"]
        needle = "2.5 mg" if use_correct_population else "No dose adjustment"
        span = next(s for s in payload["cited_evidence"][0]["proof_spans"] if needle in s["text"])
        return selected_review(schema, span["span_id"], subject="hepatic")

    monkeypatch.setattr(grounding, "structured", structured)
    result = grounding.audit_claim(cfg, claim, [{"id": "p1", "text": TEXT}], 0)
    assert result["passed"] is use_correct_population
    if not use_correct_population:
        assert "No supporting excerpt for the hepatic population." in result["issues"]


def test_source_spans_do_not_cross_population_sections():
    _, lookup = grounding.evidence_spans([{"id": "p1", "text": TEXT}])
    assert lookup
    for proof in lookup.values():
        assert proof.quote in TEXT
        assert not ("renal impairment" in proof.quote and "hepatic impairment" in proof.quote)


@pytest.mark.parametrize("case", ["contradicted", "not_supported", "counter_evidence", "incomplete"])
def test_exact_selected_proof_does_not_override_semantic_rejection(cfg, monkeypatch, case):
    def structured(cfg, schema, instruction, payload, **kwargs):
        span = payload["cited_evidence"][0]["proof_spans"][0]
        return selected_review(schema, span["span_id"],
            verdict=case if case in {"contradicted", "not_supported"} else "supported",
            counter=case == "counter_evidence", covers=case != "incomplete")

    monkeypatch.setattr(grounding, "structured", structured)
    result = grounding.audit_claim(cfg, engine.Claim(text="Test claim", evidence_ids=["p1"]),
                                   [{"id": "p1", "text": "Exact source statement."}], 0)
    assert not result["passed"] and result["issues"]


@pytest.mark.parametrize("failure", ["unknown_span", "service_unavailable"])
def test_proof_selection_fails_closed_on_invalid_references_or_audit_failure(cfg, monkeypatch, failure):
    def structured(cfg, schema, instruction, payload, **kwargs):
        if failure == "service_unavailable":
            raise TimeoutError("Test timeout")
        return selected_review(schema, "not-in-this-claim")

    monkeypatch.setattr(grounding, "structured", structured)
    result = grounding.audit_claim(cfg, engine.Claim(text="Test claim", evidence_ids=["p1"]),
                                   [{"id": "p1", "text": "Exact source statement."}], 0)
    assert not result["passed"]
    assert result["issues"][0].startswith("Claim audit unavailable")


def test_no_source_text_cannot_supply_proof(cfg, monkeypatch):
    monkeypatch.setattr(grounding, "structured", lambda *a, **kw: pytest.fail("No proof to select"))
    result = grounding.audit_claim(cfg, engine.Claim(text="Test claim", evidence_ids=["p1"]),
                                   [{"id": "p1", "text": "  \n"}], 0)
    assert not result["passed"]


@pytest.mark.parametrize("supported,assertions,expected", [
    (True, [], True), (False, ["Invented workplace"], False), (True, ["Invented workplace"], False)])
def test_personal_audit_needs_both_support_and_no_unsupported_assertions(cfg, monkeypatch, supported, assertions, expected):
    def structured(cfg, schema, instruction, payload, **kwargs):
        assert payload == {"text_to_audit": "You work at a university hospital.",
                           "PERSONAL_CONTEXT": {"HCP_A.name": "Dr. Alpha"}}
        return schema(all_assertions_supported=supported, unsupported_assertions=assertions, reason="Test audit")
    monkeypatch.setattr(grounding, "structured", structured)
    result = grounding.audit_personal(cfg, "You work at a university hospital.", {"HCP_A.name": "Dr. Alpha"})
    assert result["passed"] is expected


def test_personal_audit_empty_intro_skips_model_and_unavailable_audit_fails_closed(cfg, monkeypatch):
    def unavailable(*args, **kwargs):
        raise TimeoutError("Test timeout")
    monkeypatch.setattr(grounding, "structured", unavailable)
    assert grounding.audit_personal(cfg, "", {})["passed"]
    assert not grounding.audit_personal(cfg, "You work at a university hospital.", {})["passed"]
