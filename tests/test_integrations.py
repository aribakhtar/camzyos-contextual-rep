import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from camzyos import engine, graph, retrieval


def test_handoff_is_short_and_does_not_dump_profile():
    result = engine.handoff("Please contact an MSL", "human", {
        "HCP_A.name": "Dr Alpha", "HCP_A.personality.0": {"private": "whole personality"}},
        [{"role": "user", "content": "x" * 2000}] * 10)
    assert len(result["handoff"]["recent_conversation"]) == 4
    assert "whole personality" not in str(result)
    assert result["handoff"]["status"].endswith("not sent")


def test_page_restrictions_and_immutable_metadata(store, source):
    store.register([{**source, "title": "Changed title", "review_pages": [1]}])
    assert store.chunks() == []
    assert store.versions()[0]["source"]["title"] == "Synthetic test source"


def test_graphiti_scope_and_configured_database(cfg, monkeypatch):
    import graphiti_core
    observed = {}

    class FakeGraphiti:
        def __init__(self, **kwargs):
            observed["driver"] = kwargs["graph_driver"]

        async def search(self, query, **kwargs):
            observed.update(kwargs)
            return [SimpleNamespace(fact="own", uuid="1", group_id="hcp_HCP_A"),
                    SimpleNamespace(fact="foreign", uuid="2", group_id="hcp_HCP_B")]

        async def close(self):
            await observed["driver"].close()

    monkeypatch.setattr(graphiti_core, "Graphiti", FakeGraphiti)
    cfg["api_key"] = "test-placeholder"
    assert graph.recall(cfg, "HCP_A", "preference") == [
        {"fact": "own", "uuid": "1", "group_id": "hcp_HCP_A"}]
    assert observed["group_ids"] == ["hcp_HCP_A"]
    assert graph.retain(cfg, "HCP_A", {}, consent=False) is None


@pytest.mark.parametrize("fails", [False, True])
def test_graphiti_transports_close_before_event_loop_ends(fails):
    closed = []

    class Transport:
        def __init__(self, name):
            self.name = name

        async def close(self):
            closed.append(self.name)

    async def search(*args, **kwargs):
        if fails:
            raise RuntimeError("Synthetic search failure")
        return []

    async def close():
        closed.append("graph")
    client = SimpleNamespace(search=search, close=close, **{
        name: SimpleNamespace(client=Transport(name)) for name in ("llm_client", "embedder", "cross_encoder")})
    if fails:
        with pytest.raises(RuntimeError):
            asyncio.run(graph.memory(client, "HCP_A", query="test"))
    else:
        asyncio.run(graph.memory(client, "HCP_A", query="test"))
    assert closed == ["llm_client", "embedder", "cross_encoder", "graph"]


def test_embedding_sdk_constructor_and_dimensions(cfg, store, monkeypatch, indexed):
    import neo4j_graphrag.embeddings
    seen = []

    class Embedder:
        def __init__(self, **kwargs):
            assert "dimensions" not in kwargs  # OpenAI client constructor rejects this argument.

        def embed_query(self, text, **kwargs):
            seen.append(kwargs["dimensions"])
            return [0.1] * kwargs["dimensions"]

    class Driver:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute_query(self, query, **kwargs):
            return SimpleNamespace(records=[])

    monkeypatch.setattr(graph, "driver", lambda cfg: Driver())
    monkeypatch.setattr(neo4j_graphrag.embeddings, "OpenAIEmbeddings", Embedder)
    cfg["api_key"] = "test-placeholder"
    assert graph.sync_documents(cfg, store) == 1
    assert seen == [cfg["embedding_dimensions"]]


def test_empty_vector_results_never_fall_back_to_lexical_only(cfg, store, monkeypatch, indexed):
    cfg.update(api_key="test-placeholder", neo4j_password="test-placeholder")
    monkeypatch.setattr(graph, "vector_search", lambda *args: [])
    with pytest.raises(retrieval.RetrievalNotReady, match="no eligible passages"):
        retrieval.retrieve(cfg, store, "monitoring information")


@pytest.mark.parametrize("view", ["Chat", "Compare", "Evaluation", "Sources & updates", "Context"])
def test_streamlit_views_and_identity_reset(cfg, tables, source, store, indexed, monkeypatch, tmp_path, view):
    settings_module = importlib.import_module("camzyos.settings")
    cfg["workbook"] = tmp_path / "exists.xlsx"
    cfg["workbook"].touch()
    cfg["api_key"] = "test-placeholder"
    monkeypatch.setattr(settings_module, "settings", lambda: cfg)
    monkeypatch.setattr(settings_module, "sources", lambda cfg: [source])
    monkeypatch.setattr(engine.profiles, "load_profiles", lambda path: tables)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    app.text_input[0].set_value("a@example.test").run()
    app.radio[0].set_value(view).run()
    assert not app.exception
    if view == "Chat":
        app.chat_input[0].set_value("What should I give my patient?").run()
        assert app.session_state["messages"][-1]["result"]["decision"] == "handoff"
        app.text_input[0].set_value("b@example.test").run()
        assert app.session_state["messages"] == []
        assert not app.checkbox[0].value
        app.text_input[0].set_value("unknown@example.test").run()
        assert app.checkbox[0].disabled
        assert app.session_state["messages"] == []
        assert not app.exception
