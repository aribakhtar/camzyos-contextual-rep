"""Inspection indexing never authorizes text for clinical answers or other accounts."""
import sys
from pathlib import Path

import pytest

from camzyos import cli, engine, graph, inspection


@pytest.mark.parametrize("marker", [{"id": "inspection:us:1"}, {"corpus": "inspection"},
                                    {"clinical_evidence": False}])
def test_inspection_evidence_cannot_form_answer_schema_or_pass_validation(marker):
    passage = {"id": "ordinary", "text": "Synthetic isolation-test marker.", **marker}
    answer = engine.Answer(introduction="", context_used=[],
                           claims=[engine.Claim(text=passage["text"], evidence_ids=[passage["id"]])],
                           limitations=[], insufficient=False)
    with pytest.raises(ValueError, match="Inspection passages"):
        engine.answer_schema({"EVIDENCE": [passage], "CONTEXT": {}})
    assert not engine.validate_ids(answer, [passage], {})


def test_accidental_inspection_passage_never_reaches_generation(cfg, store, tables, monkeypatch, indexed):
    cfg["api_key"] = "test-placeholder"
    seen = []

    def classify(cfg, schema, instruction, payload):
        seen.append(schema)
        assert schema is engine.Decision
        return engine.Decision(route="answer", reason="Test", topic="general", retrieval_query="general")

    monkeypatch.setattr(engine, "parse", classify)
    monkeypatch.setattr(engine, "retrieve", lambda *a: ([{"id": "inspection:us:1", "text": "Test only"}],
                                                        "misconfigured fixture", []))
    result = engine.ask(cfg, store, tables, "a@example.test", "General product information")
    assert result["decision"] == "setup"
    assert result["citations"] == []
    assert seen == [engine.Decision]


def test_source_ownership_change_does_not_reassign_existing_passages(store, source):
    original = {**source, "account_id": "account_A"}
    store.register([original])
    store.stage(original, "private-v1", "private-hash", [{"text": "Account A fixture", "page": 1}],
                [], Path("private.pdf"))
    store.activate("private-v1", "Synthetic scoped source")
    assert len(store.chunks("account_A")) == 1
    assert store.chunks("account_B") == []
    store.register([{**original, "account_id": "account_B"}])
    assert store.chunks("account_A") == []
    assert store.chunks("account_B") == []
    assert store.chunks() == []
    assert len(store.chunks(all_accounts=True)) == 1  # Administrative indexing only.


def test_expanding_current_page_scope_does_not_approve_old_snapshot_pages(store, source):
    original = {**source, "pages": [1, 1]}
    store.register([original])
    store.stage(original, "restricted", "restricted-hash", [{"text": "Page two fixture", "page": 2}],
                [], Path("restricted.pdf"))
    store.activate("restricted", "Synthetic source")
    store.register([{**original, "pages": [1, 2]}])
    assert store.chunks() == []


@pytest.mark.parametrize("inspection_ready", [True, False])
def test_all_document_doctor_requires_both_indexes(cfg, source, monkeypatch, inspection_ready):
    cfg["api_key"] = "test-placeholder"
    monkeypatch.setattr(cli, "settings", lambda: cfg)
    monkeypatch.setattr(cli, "sources", lambda cfg: [source])
    monkeypatch.setattr(graph, "status", lambda cfg: True)
    monkeypatch.setattr(graph, "index_status", lambda *args: {"ready": True})
    monkeypatch.setattr(inspection, "report", lambda *args: {"ready": inspection_ready})
    monkeypatch.setattr(sys, "argv", ["camzyos", "doctor", "--strict", "--all-documents"])
    if inspection_ready:
        cli.main()
    else:
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 1
