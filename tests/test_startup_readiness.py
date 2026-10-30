import importlib
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from camzyos import cli, engine, graph


@pytest.mark.parametrize("key,connected,ready", [(False, True, True), (True, False, True),
                                                 (True, True, False), (True, True, True)])
def test_strict_doctor_exit_status_matches_prerequisites(cfg, store, source, monkeypatch, key, connected, ready):
    cfg["api_key"] = "test-placeholder" if key else ""
    monkeypatch.setattr(cli, "settings", lambda: cfg)
    monkeypatch.setattr(cli, "sources", lambda cfg: [source])
    monkeypatch.setattr(graph, "status", lambda cfg: connected)
    monkeypatch.setattr(graph, "index_status", lambda *args: {"ready": ready})
    monkeypatch.setattr(sys, "argv", ["camzyos", "doctor", "--strict"])
    if key and connected and ready:
        cli.main()
    else:
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 1


@pytest.mark.parametrize("ready,key", [(False, True), (True, False), (True, True)])
def test_chat_input_waits_for_index_and_key_before_any_question(
        cfg, store, tables, source, monkeypatch, ready, key):
    cfg["api_key"] = "test-placeholder" if key else ""
    settings_module = importlib.import_module("camzyos.settings")
    monkeypatch.setattr(settings_module, "settings", lambda: cfg)
    monkeypatch.setattr(settings_module, "sources", lambda cfg: [source])
    monkeypatch.setattr(engine.profiles, "load_profiles", lambda path: tables)
    monkeypatch.setattr(graph, "index_status", lambda cfg, chunks: {
        "ready": ready, "eligible_chunks": len(chunks), "indexed_chunks": len(chunks) if ready else 0})
    monkeypatch.setattr(engine, "ask", lambda *a, **k: pytest.fail("Opening chat must not invoke generation"))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert app.chat_input[0].disabled is not (ready and key)
    assert app.session_state["messages"] == []
