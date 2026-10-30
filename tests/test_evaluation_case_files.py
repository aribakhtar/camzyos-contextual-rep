import hashlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from camzyos import evaluation
from evals import retrieval as cli

CASE = {"id": "fixture", "question": "Where is the synthetic fixture excerpt?",
        "reference": "Synthetic fixture excerpt.", "reference_ids": ["fixture-v1:0"]}
SECRET = "sk-secret Authorization: Bearer private-message"


@pytest.fixture
def env(monkeypatch, tmp_path):
    evidence = [{"id": "fixture-v1:0", "version_id": "fixture-v1", "text": CASE["reference"]}]
    cfg = {"account_map": {"HCP_A": "ACCOUNT_A"}, "model": "mock-model", "embedding_model": "mock-embedding",
           "retrieval_top_k": 3, "data_dir": tmp_path, "workbook": tmp_path / "unused.xlsx",
           "api_key": SECRET, "base_url": "https://unused.invalid"}
    tables = {"HCP_Profile": [{"hcp_id": "HCP_A", "email": "a@example.test"}]}
    store = Mock()
    store.chunks.return_value = evidence
    answer = {"decision": "answer", "clinical_response": CASE["reference"], "retrieved_evidence": evidence}
    retrieve = Mock(return_value=(evidence, "mock-retrieval", []))
    ask = Mock(return_value=answer)
    judge = AsyncMock(return_value=({"context_precision": 0.5, "context_recall": 1.0,
                                    "faithfulness": 1.0}, {}, {}))
    monkeypatch.setattr(evaluation, "retrieve", retrieve)
    monkeypatch.setattr(evaluation, "ask", ask)
    monkeypatch.setattr(evaluation, "score_ragas", judge)
    monkeypatch.setattr(cli, "settings", Mock(return_value=cfg))
    monkeypatch.setattr(cli, "Store", Mock(return_value=store))
    monkeypatch.setattr(cli, "load_profiles", Mock(return_value=tables))
    return SimpleNamespace(cfg=cfg, store=store, tables=tables, evidence=evidence, retrieve=retrieve,
                           ask=ask, judge=judge)


def run_case(env, **kwargs):
    return evaluation.evaluate(env.cfg, env.store, env.tables, "a@example.test", CASE, **kwargs)


def cli_args(monkeypatch, tmp_path, items, *options):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(items), encoding="utf-8")
    output = tmp_path / "report.jsonl"
    monkeypatch.setattr(sys, "argv", ["evals.retrieval", "--cases-file", str(path),
                                     "--output", str(output), "--email", "a@example.test", *options])
    return path, output


def test_case_file_preserves_annotations_and_hashes_exact_bytes(tmp_path):
    annotated = {**CASE, "review_note": "Synthetic test only — not clinical gold."}
    raw = json.dumps([annotated], ensure_ascii=False, indent=2).encode("utf-8") + b"\r\n"
    path = tmp_path / "custom.json"
    path.write_bytes(raw)
    loaded, digest = evaluation.load_cases(path)
    assert loaded == [annotated]
    assert digest == hashlib.sha256(raw).hexdigest()
    assert evaluation.cases(path) == loaded


def test_default_cases_remain_the_four_bundled_annotations():
    assert [case["id"] for case in evaluation.cases()] == ["indication", "ingredient", "administration", "storage"]


@pytest.mark.parametrize("items", [
    None, {}, [], "cases", [None], ["case"], [CASE, CASE], [CASE, {**CASE, "id": " fixture "}],
    *[[{k: v for k, v in CASE.items() if k != field}] for field in CASE],
    *[[{**CASE, field: value}] for field in ("id", "question", "reference") for value in (None, 7, "", " \n")],
    *[[{**CASE, "reference_ids": value}] for value in
      (None, "fixture-v1:0", [], [None], [7], [""], [" \n"], ["fixture-v1:0", "fixture-v1:0"],
       ["fixture-v1:0", " fixture-v1:0 "])],
])
def test_invalid_case_shapes_are_rejected(tmp_path, items):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(items), encoding="utf-8")
    with pytest.raises(ValueError):
        evaluation.load_cases(path)


@pytest.mark.parametrize("options,items", [
    (("--repeats", "0"), [CASE]), (("--repeats", "-1"), [CASE]),
    (("--repeats", "1.5"), [CASE]), (("--repeats", "text"), [CASE]),
    (("--case", "unknown"), [CASE]), ((), []), ((), [CASE, CASE]),
])
def test_cli_rejects_invalid_input_before_setup(env, monkeypatch, tmp_path, options, items):
    _, output = cli_args(monkeypatch, tmp_path, items, *options)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    cli.settings.assert_not_called()
    cli.Store.assert_not_called()
    assert not output.exists()


@pytest.mark.parametrize("invalid", [b"not JSON", b"\xff"])
def test_cli_reports_parse_error_without_echoing_file_contents(env, monkeypatch, tmp_path, capsys, invalid):
    path, _ = cli_args(monkeypatch, tmp_path, [CASE])
    path.write_bytes(invalid + SECRET.encode())
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert SECRET not in capsys.readouterr().err
    cli.settings.assert_not_called()


def test_repeats_retain_failure_and_later_cases_with_provenance(env, monkeypatch, tmp_path, capsys):
    second = {**CASE, "id": "later", "question": "Another synthetic fixture question?"}
    path, output = cli_args(monkeypatch, tmp_path, [CASE, second], "--repeats", "3")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    env.retrieve.side_effect = [TimeoutError(SECRET)] + [(env.evidence, "mock-retrieval", [])] * 5
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    report = output.read_text(encoding="utf-8")
    records = [json.loads(line) for line in report.splitlines()]
    assert [(r["repeat_index"], r["case_id"]) for r in records] == [
        (repeat, case_id) for repeat in (1, 2, 3) for case_id in ("fixture", "later")]
    assert records[0]["result"]["decision"] == "error"
    assert records[0]["metric_errors"] == {"evaluation": "TimeoutError"}
    assert records[0]["successful"] is False
    assert all(r["successful"] for r in records[1:])
    assert all(r["cases_file_sha256"] == digest and r["cases_file"] == str(path.resolve()) for r in records)
    assert all(r["repeats"] == 3 and r["source_versions"] == ["fixture-v1"] for r in records)
    assert SECRET not in report + capsys.readouterr().out
    assert env.retrieve.call_count == 6
    env.ask.assert_not_called()
    env.store.remember.assert_not_called()


def test_cli_case_filter_default_repeat_and_hash_cover_whole_file(env, monkeypatch, tmp_path):
    path, output = cli_args(monkeypatch, tmp_path, [CASE, {**CASE, "id": "other"}], "--case", "other")
    cli.main()
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["case_id"] == "other"
    assert records[0]["repeat_index"] == records[0]["repeats"] == 1
    assert records[0]["cases_file_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("decision", ["handoff", "setup", "error"])
def test_cli_answer_failures_are_unsuccessful_without_ragas(env, monkeypatch, tmp_path, decision):
    _, output = cli_args(monkeypatch, tmp_path, [CASE], "--answers")
    env.ask.return_value = {"decision": decision, "retrieved_evidence": env.evidence}
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["result"]["decision"] == decision
    assert record["successful"] is False
    assert record["metrics"]["reference_hit_at_k"] == 1


def test_answer_run_keeps_account_scope_and_disables_memory_and_search(env):
    record = run_case(env, ragas=True)
    assert record["successful"] is True
    assert env.store.chunks.call_args_list == [call("ACCOUNT_A"), call("ACCOUNT_A")]
    env.ask.assert_called_once_with(env.cfg, env.store, env.tables, "a@example.test", CASE["question"],
                                    persist=False, search=False, mode="contextual")
    env.store.remember.assert_not_called()


@pytest.mark.parametrize("patch", [{"reference_ids": ["ineligible-v1:0"]}, {"reference": "Unpinned excerpt."}])
def test_invalid_pins_skip_judge_and_record_requested_metrics(env, patch):
    record = evaluation.evaluate(env.cfg, env.store, env.tables, "a@example.test", {**CASE, **patch}, ragas=True)
    assert record["reference_valid"] is False
    assert record["successful"] is False
    assert "reference" in record["metric_errors"]
    assert record["metrics"] == dict.fromkeys(["context_precision", "context_recall", "faithfulness"])
    assert all(name in record["metric_errors"] for name in record["metrics"])
    env.judge.assert_not_called()


def test_corpus_change_remains_an_error(env):
    env.store.chunks.side_effect = [env.evidence, [{**env.evidence[0], "id": "fixture-v2:0"}]]
    record = run_case(env, retrieval_only=True)
    assert record["result"]["decision"] == "error"
    assert record["metric_errors"] == {"evaluation": "RuntimeError"}
    assert record["successful"] is False
    assert record["metrics"] == {}


@pytest.mark.parametrize("stage", ["chunks", "ask", "retrieve"])
def test_case_exceptions_are_type_only_errors(env, stage):
    target = env.store.chunks if stage == "chunks" else getattr(env, stage)
    target.side_effect = RuntimeError(SECRET)
    record = run_case(env, retrieval_only=stage == "retrieve", ragas=True)
    assert record["result"]["decision"] == "error"
    assert record["metric_errors"]["evaluation"] == "RuntimeError"
    assert record["successful"] is False
    assert SECRET not in json.dumps(record)
    assert record["metric_errors"]["context_recall"] == "MissingMetric"


@pytest.mark.parametrize("retrieval_only", [True, False])
def test_empty_evidence_records_all_requested_metrics(env, retrieval_only):
    env.retrieve.return_value = ([], "mock-retrieval", [])
    env.ask.return_value = {"decision": "handoff"}
    record = run_case(env, ragas=True, retrieval_only=retrieval_only)
    expected = ["context_precision", "context_recall"] + ([] if retrieval_only else ["faithfulness"])
    assert record["metric_errors"] == dict.fromkeys(expected, "MissingMetric")
    assert all(record["metrics"][name] is None for name in expected)
    assert record["successful"] is False
    env.judge.assert_not_called()


def test_handoff_with_evidence_still_requires_requested_faithfulness(env):
    env.ask.return_value = {"decision": "handoff", "retrieved_evidence": env.evidence}
    env.judge.return_value = ({"context_precision": 1.0, "context_recall": 1.0}, {}, {})
    record = run_case(env, ragas=True)
    assert record["metrics"]["faithfulness"] is None
    assert record["metric_errors"] == {"faithfulness": "MissingMetric"}
    assert record["successful"] is False


def test_judge_setup_failure_retains_answer_and_reports_type_only_for_each_metric(env):
    env.judge.side_effect = ImportError(SECRET)
    record = run_case(env, ragas=True)
    assert record["result"]["decision"] == "answer"
    assert record["metrics"]["reference_hit_at_k"] == 1
    assert record["metric_errors"] == dict.fromkeys(["context_precision", "context_recall", "faithfulness"],
                                                   "ImportError")
    assert all(record["metrics"][name] is None for name in record["metric_errors"])
    assert record["successful"] is False
    assert SECRET not in json.dumps(record)


@pytest.mark.parametrize("scores", [{}, {"context_precision": 1.0},
                                  {"context_precision": 1.0, "context_recall": None}])
def test_cli_partial_judge_results_are_errors(env, monkeypatch, tmp_path, scores):
    _, output = cli_args(monkeypatch, tmp_path, [CASE], "--ragas")
    env.judge.return_value = (scores, {}, {})
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["metrics"]["context_recall"] is None
    assert record["metric_errors"]["context_recall"] == "MissingMetric"
    assert "faithfulness" not in record["metrics"]


def test_completed_low_scores_are_findings_not_execution_errors(env):
    env.judge.return_value = ({"context_precision": 0.0, "context_recall": 0.0}, {}, {})
    record = run_case(env, ragas=True, retrieval_only=True)
    assert record["successful"] is True
    assert record["metric_errors"] == {}
