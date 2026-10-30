import copy
import importlib
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import BaseModel, ValidationError
from streamlit.testing.v1 import AppTest

from camzyos import conversation as chat
from camzyos import engine
from camzyos.llm import ContextBudgetExceeded


class FixtureOutput(BaseModel):
    value: str


def transcript(count=60, identity="HCP_A"):
    return [{"id": f"m{i}", "timestamp": f"2026-10-30T10:{i // 60:02}:{i % 60:02}+00:00",
             "hcp_id": identity, "role": "user" if i % 2 == 0 else "assistant",
             "content": f"Turn {i}. " + "Synthetic conversation detail. " * 25} for i in range(count)]


@pytest.fixture
def compact(cfg, monkeypatch):
    cfg.update(context_window_tokens=4000, max_output_tokens=300, context_safety_margin_tokens=128,
               conversation_summary_batch_tokens=900, conversation_summary_tokens=400,
               conversation_compact_at=0.5)
    calls = []

    def summarize(cfg, schema, instruction, payload, **kwargs):
        calls.append(copy.deepcopy(payload))
        old = payload["prior_summary"]
        first = old["notes"][0]["message_ids"][0] if old else payload["messages"][0]["id"]
        last = payload["messages"][-1]["id"]
        return chat.Summary(notes=[chat.Note(text="Historical discussion; no medical evidence.", message_ids=[first])],
                            unresolved=[chat.Note(text="A question remains recorded as open.", message_ids=[last])])

    monkeypatch.setattr(chat, "structured", summarize)
    return cfg, calls


def test_normalizes_dated_pairs_without_dropping_any_turn():
    history = [{"question": str(i), "answer": "reply", "created": "2026-10-30T00:00:00+00:00"}
               for i in range(20)]
    rows = chat.normalize(history, "HCP_A")
    assert len(rows) == 40 and len({m["id"] for m in rows}) == 40
    assert rows[0]["content"] == "0" and rows[-2]["content"] == "19"
    assert all(m["timestamp"] == history[0]["created"] for m in rows)


def test_full_short_history_reaches_prompt_without_summary(cfg, monkeypatch):
    raw = transcript(10)
    summarize = Mock(side_effect=AssertionError("Short history should not need summary"))
    monkeypatch.setattr(chat, "structured", summarize)
    working = chat.WorkingConversation(cfg, raw, "HCP_A")
    payload = working.fit(FixtureOutput, "Test instruction", {"question": "Next?"})
    assert len(payload["conversation"]) == 10
    assert working.report()["summarized_messages"] == 0
    summarize.assert_not_called()


def test_compaction_preserves_all_raw_messages_dates_and_cached_prefix(compact):
    cfg, calls = compact
    raw = transcript()
    original = copy.deepcopy(raw)
    state = {}
    working = chat.WorkingConversation(cfg, raw, "HCP_A", state)
    payload = working.fit(FixtureOutput, "Test", {"question": "Next?"})
    assert calls and state["covered_count"] == 54
    assert raw == original and working.rows == original
    assert payload["conversation"] == raw[-6:]
    assert payload["conversation_summary"]["from"] == raw[0]["timestamp"]
    assert payload["conversation_summary"]["through"] == raw[53]["timestamp"]
    assert state["summary"]["notes"][0]["message_ids"] == ["m0"]
    count = len(calls)
    again = chat.WorkingConversation(cfg, raw, "HCP_A", state)
    again.fit(FixtureOutput, "Test", {"question": "Next?"})
    assert len(calls) == count
    assert again.report()["transcript_truncated"] is False


def test_changed_prefix_and_foreign_summary_are_not_reused(compact):
    cfg, calls = compact
    raw = transcript()
    state = {}
    chat.WorkingConversation(cfg, raw, "HCP_A", state).fit(FixtureOutput, "Test", {})
    raw[0]["content"] = "Changed user correction"
    rebuilt = chat.WorkingConversation(cfg, raw, "HCP_A", state)
    assert rebuilt.state["covered_count"] == 0
    rebuilt.fit(FixtureOutput, "Test", {})
    foreign = chat.WorkingConversation(cfg, [], "HCP_B", state)
    assert foreign.state["summary"] is None and foreign.state["hcp_id"] == "HCP_B"
    with pytest.raises(ValueError, match="different HCP"):
        chat.WorkingConversation(cfg, raw, "HCP_B")


def test_old_safety_indicator_survives_a_summary_that_omits_it(compact):
    cfg, _ = compact
    raw = transcript()
    raw[0]["content"] = "My patient fainted after treatment."
    working = chat.WorkingConversation(cfg, raw, "HCP_A", rule=lambda text: "patient" if "My patient" in text else None)
    payload = working.fit(FixtureOutput, "Test", {"question": "What should I do for that person?"})
    assert "fainted" not in str(payload["conversation"])
    assert {s["kind"] for s in payload["conversation_safety"]} >= {"patient", "adverse_event"}
    assert all(s["first_message_id"] == "m0" for s in payload["conversation_safety"])


@pytest.mark.parametrize("failure", ["api", "foreign_id", "too_long"])
def test_summary_failure_never_clips_or_sends_partial_history(compact, monkeypatch, failure):
    cfg, _ = compact
    raw = transcript()
    original = copy.deepcopy(raw)
    def broken(*args, **kwargs):
        if failure == "api":
            raise TimeoutError("test secret")
        return chat.Summary(notes=[chat.Note(text="Long text. " * (600 if failure == "too_long" else 1),
                                            message_ids=["FOREIGN" if failure == "foreign_id" else "m0"])], unresolved=[])
    monkeypatch.setattr(chat, "structured", broken)
    working = chat.WorkingConversation(cfg, raw, "HCP_A")
    with pytest.raises((TimeoutError, ValueError)):
        working.fit(FixtureOutput, "Test", {})
    assert raw == original and working.state["covered_count"] == 0


def test_oversized_current_message_is_not_cut_or_silently_sent(compact, monkeypatch):
    cfg, calls = compact
    question = "Long request. " * 10000
    working = chat.WorkingConversation(cfg, [], "HCP_A")
    with pytest.raises(ContextBudgetExceeded):
        working.fit(FixtureOutput, "Test", {"question": question})
    assert not calls


def test_summary_schema_only_allows_ids_from_the_supplied_batch_or_prior_summary(compact, monkeypatch):
    cfg, _ = compact
    raw = transcript(4)
    def check_schema(config, schema, instruction, payload, **kwargs):
        valid = {"notes": [{"subject": "hcp", "text": "Historical note", "message_ids": [payload["messages"][0]["id"]]}],
                 "unresolved": []}
        parsed = schema.model_validate(valid)
        with pytest.raises(ValidationError):
            schema.model_validate({"notes": [{"text": "Invented reference", "message_ids": ["foreign"]}],
                                   "unresolved": []})
        assert parsed.notes[0].subject == "hcp"
        return parsed
    monkeypatch.setattr(chat, "structured", check_schema)
    working = chat.WorkingConversation(cfg, raw, "HCP_A")
    working.compact(2)
    assert working.state["covered_count"] == 2 and working.rows == raw


def test_saved_transcript_roundtrip_exceeds_old_eight_record_limit(store):
    for i in range(12):
        store.remember("HCP_A", {"question": f"question {i}", "answer": "reply", "decision": "handoff",
            "question_id": f"q{i}", "answer_id": f"a{i}", "policy_route": "patient"}, consent=True)
    store.remember("HCP_B", {"question": "foreign"}, consent=True)
    assert len(store.history("HCP_A")) == 12
    rows = store.conversation_history("HCP_A")
    assert len(rows) == 24 and rows[0]["id"] == "q0" and rows[-1]["id"] == "a11"
    assert rows[1]["policy_route"] == "patient" and all(row["timestamp"] for row in rows)
    assert "foreign" not in str(rows)


def test_summary_persistence_requires_covered_message_consent_and_forget_is_scoped(store):
    store.remember("HCP_A", {"question": "saved", "question_id": "saved-id"}, consent=True)
    state = {"hcp_id": "HCP_A", "covered_count": 1, "covered_message_ids": ["unsaved-id"],
             "summary": {"notes": ["unsaved private material"]}}
    assert not store.save_conversation_state("HCP_A", state, consent=True)
    assert store.conversation_state("HCP_A") == {}
    state.update(covered_message_ids=["saved-id"], summary={"notes": []})
    assert not store.save_conversation_state("HCP_A", state, consent=False)
    assert store.save_conversation_state("HCP_A", state, consent=True)
    with pytest.raises(ValueError):
        store.save_conversation_state("HCP_B", state, consent=True)
    store.remember("HCP_B", {"question": "keep"}, consent=True)
    store.delete_history("HCP_A")
    assert store.conversation_history("HCP_A") == [] and store.conversation_state("HCP_A") == {}
    assert store.history("HCP_B") == [{"question": "keep"}]


def test_handoffs_are_retained_only_with_consent(cfg, store, tables):
    engine.ask(cfg, store, tables, "a@example.test", "Please contact an MSL", persist=False)
    assert store.history("HCP_A") == []
    result = engine.ask(cfg, store, tables, "a@example.test", "Please contact an MSL", persist=True)
    assert result["decision"] == "handoff"
    assert store.history("HCP_A")[0]["decision"] == "handoff"
    assert len(store.conversation_history("HCP_A")) == 2


def test_enabling_saving_does_not_copy_unsaved_history_into_a_handoff(cfg, store, tables):
    raw = [chat.message("user", "My patient fainted; this earlier turn was not saved.", "HCP_A")]
    state = {}
    working = chat.WorkingConversation(cfg, raw, "HCP_A", state)
    state.update(covered_count=1, covered_message_ids=[raw[0]["id"]], prefix_hash=chat.digest(working.rows),
                 summary={"notes": [{"text": "Earlier unsaved patient details", "message_ids": [raw[0]["id"]]}],
                          "unresolved": []})
    result = engine.ask(cfg, store, tables, "a@example.test", "Please contact an MSL", history=raw,
                        persist=True, conversation_state=state)
    assert result["handoff"]["recent_conversation"][0]["text"] == raw[0]["content"]
    assert result["handoff"]["historical_summary"]
    saved = store.history("HCP_A")[0]
    assert saved["handoff"]["recent_conversation"] == []
    assert saved["handoff"]["historical_summary"] is None
    assert saved["handoff"]["safety_context"] == []
    assert saved["handoff"]["history_message_count"] == 0
    assert raw[0]["content"] not in str(saved) and raw[0]["id"] not in str(saved)
    assert store.conversation_state("HCP_A") == {}
    assert len(store.conversation_history("HCP_A")) == 2


def test_ui_preserves_history_across_hcp_switch_and_clears_only_explicitly(cfg, tables, source, store,
                                                                         indexed, monkeypatch, tmp_path):
    cfg.update(api_key="test-placeholder", workbook=tmp_path / "exists.xlsx")
    cfg["workbook"].touch()
    settings = importlib.import_module("camzyos.settings")
    monkeypatch.setattr(settings, "settings", lambda: cfg)
    monkeypatch.setattr(settings, "sources", lambda _: [source])
    monkeypatch.setattr(engine.profiles, "load_profiles", lambda _: tables)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    app.text_input[0].set_value("a@example.test").run()
    original = [chat.message("user", f"Historical note {i}", "HCP_A") for i in range(15)]
    app.session_state.messages = copy.deepcopy(original)
    app.run()
    app.chat_input[0].set_value("Please contact an MSL").run()
    assert not app.exception and len(app.session_state.messages) == 17
    app.text_input[0].set_value("b@example.test").run()
    assert app.session_state.messages == []
    app.text_input[0].set_value("a@example.test").run()
    assert len(app.session_state.messages) == 17
    assert app.session_state.messages[:15] == original
    next(b for b in app.button if b.label == "Clear this conversation").click().run()
    assert app.session_state.messages == [] and not app.exception
