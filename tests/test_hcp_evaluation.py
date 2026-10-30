import copy
import json
from unittest.mock import Mock

import pytest

from evals import hcp

PROFILE = {"hcp_id": "HCP_TEST", "name": "Test HCP", "email": "test@example.test"}
TABLES = {"HCP_Profile": [PROFILE], "Approved_Content": [
    {"content_id": "CNT_TEST", "summary": "Synthetic fixture, not clinical evidence."}]}
CASE = {"id": "test_1", "hcp_id": PROFILE["hcp_id"], "hcp_name": PROFILE["name"],
        "login_email": PROFILE["email"], "as_of_date": "2026-10-30", "category": "label_specifics",
        "question": "A synthetic test question", "expected_decision": "partial_answer",
        "expected_behavior": "Give supported information and acknowledge limits.",
        "expected_sources": ["CNT_TEST"], "guardrails": [], "grounded_in": []}


def test_input_is_preserved_exactly_and_identity_validated(tmp_path):
    path = tmp_path / "cases.json"
    raw = b"\xef\xbb\xbf" + json.dumps([CASE], indent=2).encode() + b"\r\n"
    path.write_bytes(raw)
    assert hcp.load_cases(path, TABLES) == ([CASE], raw)
    path.write_text(json.dumps([{**CASE, "hcp_id": "FOREIGN"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="workbook HCP"):
        hcp.load_cases(path, TABLES)


@pytest.mark.parametrize("cases", [[], [CASE, CASE], [{**CASE, "question": ""}],
    [{**CASE, "expected_sources": "CNT_TEST"}], [{**CASE, "expected_decision": "invented"}]])
def test_invalid_cases_fail_before_execution(tmp_path, cases):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    with pytest.raises(ValueError):
        hcp.load_cases(path, TABLES)


def test_workbook_references_never_become_medical_gold():
    audit = hcp.audit_case({**CASE, "expected_sources": ["CNT_TEST", "MISSING"]}, TABLES, set())
    assert [r["status"] for r in audit["references"]] == [
        "synthetic_not_clinical_evidence", "missing_workbook_record"]
    assert audit["has_clinical_gold"] is False
    assert audit["context_precision"] is None and audit["context_recall"] is None
    assert audit["literal_decision_supported"] is False


def test_multiturn_uses_actual_reply_and_does_not_persist(monkeypatch):
    case = {**CASE, "category": "conversation_context", "expected_decision": "handoff",
            "question": "[Turn 1] Initial request. [Turn 2, assistant invents text] [Turn 3] Follow up?"}
    calls = []

    def ask(*args, **kwargs):
        calls.append((args, copy.deepcopy(kwargs)))
        return {"decision": "handoff", "answer": "Actual first reply" if len(calls) == 1 else "Final reply"}

    monkeypatch.setattr(hcp, "snapshot", lambda *_: "frozen")
    monkeypatch.setattr(hcp.engine, "ask", ask)
    result = hcp.execute_case({}, None, TABLES, case, "frozen", {})
    assert result["execution_completed"] and result["literal_decision_match"]
    assert len(calls) == 2
    assert calls[1][1]["history"] == [{"role": "user", "content": "Initial request."},
                                      {"role": "assistant", "content": "Actual first reply"}]
    assert all(c[1]["persist"] is False and c[1]["search"] is False for c in calls)
    assert result["scenario_adaptation"]["provided_assistant_description"] == "assistant invents text"


def test_code_change_stops_case_before_model_call(monkeypatch):
    monkeypatch.setattr(hcp, "snapshot", lambda *_: "changed")
    ask = Mock()
    monkeypatch.setattr(hcp.engine, "ask", ask)
    result = hcp.execute_case({}, None, TABLES, CASE, "original", {})
    assert not result["execution_completed"]
    assert result["error"] == "RuntimeError"
    ask.assert_not_called()


def test_trace_keeps_initial_payload_before_revision_mutates_it():
    hcp.TRACE.calls = []
    payload = {"question": "initial"}
    response = Mock()
    response.model_dump.return_value = {"answer": "first"}
    assert hcp.trace_parse(lambda *_: response)({}, hcp.Judgment, "instruction", payload) is response
    payload["question"] = "changed"
    assert hcp.TRACE.calls[0]["input"]["question"] == "initial"
    hcp.TRACE.calls = []


def test_judge_error_is_retained_without_rerunning_chat_or_exposing_secret(monkeypatch):
    monkeypatch.setattr(hcp, "OpenAI", Mock(side_effect=RuntimeError("sk-sensitive-test-value")))
    ask = Mock()
    monkeypatch.setattr(hcp.engine, "ask", ask)
    record = {"case_id": CASE["id"], "case": CASE, "execution_completed": True, "audit": {}, "turns": []}
    result = hcp.score_case({"model": "mock", "api_key": "private", "base_url": "unused"}, TABLES, record, False)
    assert result["errors"] == {"behavior": "RuntimeError"}
    assert "sensitive" not in json.dumps(result)
    ask.assert_not_called()


def test_missing_scores_not_counted_as_zero_or_success():
    records = [{"case_id": CASE["id"], "case": CASE, "execution_completed": True,
                "literal_decision_match": False, "result": {"decision": "handoff"}}]
    scores = [{"case_id": CASE["id"], "behavior": None, "errors": {"behavior": "TimeoutError"},
               "faithfulness": {"value": None, "status": "not_applicable_no_clinical_answer"}}]
    result = hcp.summarize(records, scores)
    assert result["faithfulness_mean"] is None
    assert result["faithfulness_scored_answers"] == result["behavior_judgments"] == 0
    assert result["judge_errors"]["behavior"] == 1
