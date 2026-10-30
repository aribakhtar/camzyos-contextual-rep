"""Memory seed regressions with an in-memory Graphiti boundary; no network calls."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import NAMESPACE_URL, uuid5

import pytest
from graphiti_core.nodes import EpisodeType, EpisodicNode

from camzyos import graph


@pytest.fixture
def memory_backend(monkeypatch):
    backend = SimpleNamespace(episodes=[], clients=[], fail_next=False)
    precreate = AsyncMock(side_effect=AssertionError("Do not pre-create an empty seed episode"))
    monkeypatch.setattr(EpisodicNode, "save", precreate)

    def client_factory(cfg):
        async def lookup(query, *, name, uuid, group):
            # Assert the Cypher boundary too: passing group alone does not scope a query.
            compact = "".join(query.split())
            assert compact.startswith("MATCH(n:Episodic{group_id:$group})WHERE")
            assert "n.name=$nameORn.uuid=$uuid" in compact
            assert compact.endswith("RETURNn.uuidASuuid")  # Lookup must remain read-only.
            return ([{"uuid": row["uuid"]} for row in backend.episodes
                     if row["group_id"] == group and (row["name"] == name or row["uuid"] == uuid)], None, None)

        async def add_episode(**kwargs):
            assert "uuid" not in kwargs  # Graphiti 0.31.2 interprets this as an existing episode.
            if backend.fail_next:
                backend.fail_next = False
                raise RuntimeError("Synthetic extraction failure")
            episode = {**kwargs, "uuid": f"graphiti-generated-{len(backend.episodes) + 1}"}
            backend.episodes.append(episode)
            return SimpleNamespace(episode=SimpleNamespace(uuid=episode["uuid"]))

        client = SimpleNamespace(
            driver=SimpleNamespace(execute_query=AsyncMock(side_effect=lookup)),
            build_indices_and_constraints=AsyncMock(), add_episode=AsyncMock(side_effect=add_episode),
            close=AsyncMock(), **{name: SimpleNamespace(client=SimpleNamespace(close=AsyncMock()))
                                 for name in ("llm_client", "embedder", "cross_encoder")})
        backend.clients.append(client)
        return client

    monkeypatch.setattr(graph, "memory_client", client_factory)
    yield backend
    precreate.assert_not_awaited()
    # This covers successful extraction, unchanged/legacy early returns, and failure.
    for client in backend.clients:
        client.close.assert_awaited_once()
        for component in ("llm_client", "embedder", "cross_encoder"):
            getattr(client, component).client.close.assert_awaited_once()


def test_first_seed_unchanged_skip_and_changed_context(memory_backend):
    context = {"language": "de", "preference": "brief"}
    first = graph.retain({}, "HCP_A", context, consent=True, seed=True)
    added = memory_backend.clients[0].add_episode.await_args.kwargs
    assert "uuid" not in added
    assert added["group_id"] == "hcp_HCP_A"
    assert added["source"] == EpisodeType.json
    assert json.loads(added["episode_body"]) == context
    assert first == {"episode_uuid": memory_backend.episodes[0]["uuid"]}

    # Object key ordering must not cause another extraction.
    unchanged = graph.retain({}, "HCP_A", dict(reversed(list(context.items()))), consent=True, seed=True)
    assert unchanged == {**first, "status": "already imported"}
    memory_backend.clients[1].add_episode.assert_not_awaited()
    assert first["episode_uuid"] != memory_backend.clients[1].driver.execute_query.await_args.kwargs["uuid"]

    changed_context = {**context, "preference": "detailed"}
    changed = graph.retain({}, "HCP_A", changed_context, consent=True, seed=True)
    assert changed["episode_uuid"] != first["episode_uuid"]
    assert len(memory_backend.episodes) == 2
    assert memory_backend.episodes[0]["name"] != memory_backend.episodes[1]["name"]
    assert json.loads(memory_backend.episodes[1]["episode_body"]) == changed_context


def test_seed_lookup_excludes_foreign_hcp_and_accepts_legacy_uuid(memory_backend):
    context = {"preference": "brief"}
    legacy_uuid = str(uuid5(NAMESPACE_URL, "HCP_A" + json.dumps(context, sort_keys=True)))
    # Even an identically named episode in another HCP's group must not skip this seed.
    memory_backend.episodes.append({"name": f"Attributed HCP context seed:{legacy_uuid}",
                                    "uuid": "foreign-episode", "group_id": "hcp_HCP_B"})
    own = graph.retain({}, "HCP_A", context, consent=True, seed=True)
    assert own["episode_uuid"] != "foreign-episode"
    memory_backend.clients[0].add_episode.assert_awaited_once()
    assert memory_backend.clients[0].driver.execute_query.await_args.kwargs["group"] == "hcp_HCP_A"
    assert memory_backend.episodes[-1]["group_id"] == "hcp_HCP_A"

    # Represent the same content imported by the old helper, with its old name/UUID.
    memory_backend.episodes[-1].update(name="Attributed HCP context", uuid=legacy_uuid)
    legacy = graph.retain({}, "HCP_A", context, consent=True, seed=True)
    assert legacy == {"episode_uuid": legacy_uuid, "status": "already imported"}
    memory_backend.clients[1].add_episode.assert_not_awaited()
    assert len(memory_backend.episodes) == 2


def test_failed_extraction_leaves_no_empty_episode_and_can_retry(memory_backend):
    context = {"preference": "brief"}
    memory_backend.fail_next = True
    with pytest.raises(RuntimeError, match="Synthetic extraction failure"):
        graph.retain({}, "HCP_A", context, consent=True, seed=True)
    assert memory_backend.episodes == []

    retried = graph.retain({}, "HCP_A", context, consent=True, seed=True)
    failed_client, retry_client = memory_backend.clients
    assert failed_client.add_episode.await_args.kwargs["name"] == retry_client.add_episode.await_args.kwargs["name"]
    retry_client.add_episode.assert_awaited_once()
    assert retried == {"episode_uuid": memory_backend.episodes[0]["uuid"]}
    assert len(memory_backend.episodes) == 1
