import copy
import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from evals import contextualization as metrics
from evals.contextualization_recovery import APPLICABILITY_ERROR, recover

TABLES = {"HCP_Profile": [{"hcp_id": "HCP_A", "name": "Demo A", "email": "a@example.test", "language": "German"}]}
RECORD = {"case_id": "a1", "hcp_id": "HCP_A", "execution_completed": True,
    "case": {"login_email": "a@example.test", "as_of_date": "2026-10-30", "category": "preference",
             "expected_behavior": "UNTRUSTED_EXPECTATION", "expected_decision": "answer"},
    "turns": [{"question": "Please answer in English.", "result": {"answer": "You prefer German."}}],
    "result": {"decision": "answer", "answer": "You prefer German.", "context_used": {}}, "trace": []}


def assessment():
    criterion = {"verdict": "not_applicable", "rationale": "No requirement", "output_quotes": []}
    return metrics.Assessment(personal_claims=[metrics.PersonalClaim(output_quote="You prefer German.",
        kind="preference", verdict="supported", source_ids=["HCP_A.language"], rationale="Profile")],
        personalization_applicable=True, personalization_level=1, personalization_rationale="Only preference mentioned",
        response_language="English",
        **{name: copy.deepcopy(criterion) for name in metrics.CRITERIA})


def test_context_judge_does_not_receive_author_expected_behavior_or_decision():
    payload = metrics.payload_for(TABLES, RECORD)
    assert "UNTRUSTED_EXPECTATION" not in json.dumps(payload)
    assert "expected_decision" not in payload
    assert payload["sources"]["HCP_A.language"] == "German"
    assert payload["actual_turns"][0]["actual_answer"] == "You prefer German."
    assert payload["sources"]["turn:0:user"]["text"] == "Please answer in English."
    assert payload["language_policy"] == {"target": "English", "basis": "explicit request"}


def test_question_language_alone_does_not_override_hcp_language():
    record = copy.deepcopy(RECORD)
    record["turns"][0]["question"] = "Can you help?"
    assert metrics.payload_for(TABLES, record)["language_policy"] == {"target": "German", "basis": "HCP profile"}


def test_context_judge_rejects_wrong_hcp_identity():
    with pytest.raises(ValueError, match="mismatch"):
        metrics.payload_for(TABLES, {**RECORD, "hcp_id": "HCP_B"})


@pytest.mark.parametrize("bad", ["invented_quote", "foreign_source", "ungrounded_support", "false_multiturn"])
def test_judge_observations_need_actual_quotes_valid_ids_and_real_history(bad):
    result = assessment()
    if bad == "invented_quote":
        result.personal_claims[0].output_quote = "This text never occurred."
    elif bad == "foreign_source":
        result.personal_claims[0].source_ids = ["HCP_B.language"]
    elif bad == "ungrounded_support":
        result.personal_claims[0].source_ids = []
    else:
        result.conversation_followup.verdict = "met"
    with pytest.raises(ValueError):
        metrics.validate_assessment(result, metrics.payload_for(TABLES, RECORD))


def test_unsupported_claim_is_retained_without_inventing_a_reference():
    result = assessment()
    result.personal_claims[0].verdict = "unsupported"
    result.personal_claims[0].source_ids = []
    metrics.validate_assessment(result, metrics.payload_for(TABLES, RECORD))


def test_metric_denominators_exclude_missing_and_not_applicable_without_rewarding_them():
    first = assessment().model_dump()
    first["language"]["verdict"] = "not_met"
    first["personal_claims"][0]["verdict"] = "contradicted"
    second = assessment().model_dump()
    second["personal_claims"][0]["kind"] = "identity"
    second["personalization_applicable"] = False
    rows = [{"status": "scored", "assessment": first}, {"status": "scored", "assessment": second},
            {"status": "error"}]
    summary = metrics.summarize(rows)
    assert summary["cases"] == 3 and summary["scored"] == 2
    assert summary["language"]["met_rate"] == 0 and summary["language"]["assessed_cases"] == 1
    assert summary["conversation_followup"]["met_rate"] is None
    assert summary["substantive_personal_claims"]["support_rate"] == 0
    assert summary["all_personal_claims"]["support_rate"] == 0.5
    assert summary["personalization"]["applicable_cases"] == 1


def test_empty_claims_are_not_a_perfect_grounding_score():
    result = assessment().model_dump()
    result["personal_claims"] = []
    summary = metrics.summarize([{"status": "scored", "assessment": result}])
    assert summary["all_personal_claims"]["support_rate"] is None


def test_metric_api_error_is_recorded_without_exposing_credentials(monkeypatch):
    monkeypatch.setattr(metrics, "OpenAI", Mock(side_effect=RuntimeError("sk-sensitive-test")))
    row = metrics.score_case({"model": "fixture", "api_key": "secret", "base_url": "unused"}, TABLES, RECORD)
    assert row["status"] == "error" and row["error"] == "RuntimeError"
    assert "sensitive" not in json.dumps(row) and "secret" not in json.dumps(row)


def test_recovery_only_corrects_known_single_turn_applicability_without_new_judgment():
    original = assessment().model_dump()
    original["conversation_followup"]["verdict"] = "met"
    row = {"status": "error", "validation_error": APPLICABILITY_ERROR, "unvalidated_assessment": original}
    before = copy.deepcopy(row)
    fixed = recover(row, RECORD, TABLES)
    assert row == before
    assert fixed["assessment"]["conversation_followup"]["verdict"] == "not_applicable"
    assert fixed["assessment"]["personal_claims"] == original["personal_claims"]
    assert fixed["recovery"]["new_model_calls"] == 0
    assert recover({**row, "validation_error": "Personal claim quote is absent from the answer."}, RECORD, TABLES) is None


def test_applicability_recovery_cannot_bypass_quote_validation():
    original = assessment().model_dump()
    original["personal_claims"][0]["output_quote"] = "Invented output"
    row = {"status": "error", "validation_error": APPLICABILITY_ERROR, "unvalidated_assessment": original}
    with pytest.raises(ValueError, match="quote"):
        recover(row, RECORD, TABLES)


def test_single_turn_schema_prevents_followup_applicability_errors_before_scoring():
    schema = metrics.assessment_schema(metrics.payload_for(TABLES, RECORD))
    candidate = assessment().model_dump()
    schema.model_validate(candidate)
    candidate["conversation_followup"]["verdict"] = "met"
    with pytest.raises(ValidationError):
        schema.model_validate(candidate)
