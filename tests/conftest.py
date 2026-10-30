from pathlib import Path

import pytest

from camzyos.settings import settings
from camzyos.store import Store


@pytest.fixture
def indexed(monkeypatch):
    """Synthetic ready index for answer-policy tests; readiness has separate failure tests."""
    from camzyos import graph, grounding
    monkeypatch.setattr(graph, "index_status", lambda cfg, chunks: {
        "ready": bool(chunks), "eligible_chunks": len(chunks), "indexed_chunks": len(chunks),
        "index_state": "ONLINE", "missing_ids": []})
    monkeypatch.setattr(graph, "vector_search", lambda cfg, query, chunks: [c["id"] for c in chunks])
    # Existing orchestration tests isolate the external claim-audit dependency. Its semantic,
    # quotation and failure-boundary behavior is exercised separately in test_grounding_policy.py.
    monkeypatch.setattr(grounding, "audit", lambda *args: {"passed": True, "claims": [], "issues": []})
    monkeypatch.setattr(grounding, "audit_personal", lambda *args: {"passed": True, "reason": "Fixture audit"})


@pytest.fixture
def cfg(tmp_path):
    return {**settings(), "data_dir": tmp_path, "api_key": "", "neo4j_password": "",
            "graphiti_enabled": False, "reranking_enabled": False}


@pytest.fixture
def source():
    return {"id": "test", "title": "Synthetic test source", "market": "DE", "audience": "HCP",
            "eligible": True, "kind": "label", "contribution": "Test only"}


@pytest.fixture
def store(tmp_path, source):
    db = Store(tmp_path)
    db.register([source])
    db.stage(source, "v1", "hash1", [{"text": "Monitoring information is in this synthetic test document.",
             "page": 1, "page_end": 1, "section": "Test"}], [], Path("test.pdf"))
    db.activate("v1", "Synthetic test fixture, not medical evidence")
    return db


@pytest.fixture
def tables():
    return {"HCP_Profile": [
        {"hcp_id": "HCP_A", "name": "Dr. Alpha", "email": "a@example.test", "language": "German",
         "communicationStyle": "Concise", "camzyos_experience": "Never initiated"},
        {"hcp_id": "HCP_B", "name": "Dr. Beta", "email": "b@example.test", "language": "German",
         "communicationStyle": "Detailed"}],
        "Personality": [{"hcp_id": "HCP_A", "concern": "A only"},
                        {"hcp_id": "HCP_B", "concern": "B secret"}],
        "HCP_Interactions": [{"hcp_id": "HCP_A", "interaction_id": "IA", "notes": "A history"},
                             {"hcp_id": "HCP_B", "interaction_id": "IB", "notes": "B secret"}]}

