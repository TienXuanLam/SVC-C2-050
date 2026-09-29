# SVC-C2-050 — Integration Tests: HTTP entry point (endpoint-level trust gate)
#
# Uses FastAPI's TestClient against the real src.api.server.app — no live
# socket, but exercises the actual /invoke handler (INVOKE_AUTH_TOKEN check,
# ctx construction, agent.invoke()) rather than only unit-testing individual
# nodes. Complements tests/unit/test_output_validate_node.py's node-level
# trust-gate test (unit tests can't prove the endpoint itself enforces auth).

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("INVOKE_AUTH_TOKEN", "test-endpoint-token")
    # Re-import fresh so the module-level `agent`/token read happens under
    # this fixture's env var (src.api.server reads INVOKE_AUTH_TOKEN
    # per-request inside the handler, not at import time, so a plain import
    # is sufficient here — no importlib.reload needed).
    from src.api.server import app

    return TestClient(app)


def _payload(mode: str = "template_only") -> dict:
    return {
        "input": json.dumps(
            {
                "mode": mode,
                "event_type": "conference",
                "attendee_count": 150,
                "duration_days": 2,
                "venue_type": "convention_center",
                "format": "in_person",
                "event_name": "Annual Partner Summit",
            }
        ),
        "session_id": "test-session",
    }


def test_health_endpoint_no_auth_required(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_invoke_without_token_returns_401(client):
    """Anonymous caller with no bearer token must be rejected at the
    entry-point boundary (before any node runs), not silently downgraded."""
    resp = client.post("/invoke", json=_payload())
    assert resp.status_code == 401


def test_invoke_with_wrong_token_returns_401(client):
    resp = client.post("/invoke", json=_payload(), headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


def test_invoke_with_correct_token_reaches_the_agent(client):
    """With a valid bearer token the caller runs at VERIFIED_EXTERNAL and the
    request reaches the agent. template_only mode needs no LLM, so this also
    proves the full pipeline (no ANTHROPIC_API_KEY configured in this test
    environment) succeeds end-to-end via the real HTTP entry point."""
    resp = client.post("/invoke", json=_payload("template_only"), headers={"Authorization": "Bearer test-endpoint-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "InitializeNode" in body["node_history"]
    assert "EventParamIngestNode" in body["node_history"]
