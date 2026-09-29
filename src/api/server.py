"""AgentCore Platform v1.0"""

# Standalone HTTP entry point for the agent.
# Entry points are adapters only — no business logic here.
# For platform-level routing, AgentGateway calls agent.invoke() directly.

import os
import secrets
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from shared.secrets import factory as secrets_factory
from src.graph.graph import MICEEventPlanningChecklistVendorBriefGenerationAgent

app = FastAPI(title="Agent")

# AnthropicClient (shared.services.llm.anthropic_client) requires config["api_key"]
# at construction time — but construction happens once at module load, before
# any per-request InvocationContext exists (ctx.secrets is only bound per
# invoke). Resolve the provider first and read the key directly from it here;
# this mirrors the entry-point exception already used below for
# INVOKE_AUTH_TOKEN — a bootstrap-time credential read, not a bypass of
# ctx.secrets inside a node.
#
# Import is deferred inside the `if` for symmetry with the no-key path:
# ChecklistGenerateNode/VendorBriefDraftNode/TimelineGenerateNode all fail
# closed via their own "LLM client not configured" check when llm=None — a
# fully supported, tested state (template_only mode needs no LLM at all).
_secrets_provider = secrets_factory(namespace="svc", agent_name="MICEEventPlanningChecklistVendorBriefGenerationAgent")
_anthropic_api_key = _secrets_provider.get("ANTHROPIC_API_KEY")
if _anthropic_api_key:
    try:
        from shared.services.llm.anthropic_client import AnthropicClient
    except ModuleNotFoundError as exc:
        # Preflight failure, not a bare traceback: ANTHROPIC_API_KEY IS
        # configured (the deployer intends full_generation mode to work),
        # but the package needed to honor that is missing — fail loudly and
        # actionably at startup instead of a confusing import stack trace,
        # and instead of silently falling back to llm=None (which would make
        # every full_generation invocation fail per-request with a much less
        # obvious "LLM client not configured" error).
        raise RuntimeError(
            "ANTHROPIC_API_KEY is configured but langchain-anthropic is not "
            "installed. See pyproject.toml dependencies."
        ) from exc

    _llm = AnthropicClient(config={"api_key": _anthropic_api_key})
else:
    _llm = None

# The standalone entry point does not get config/config.yaml for free — only
# the platform-managed AgentRegistry path reads it automatically. Read it
# explicitly here so max_retry/memory_enabled/timeout_s and the Config
# Surface (kb_path/system_prompt) actually reach the compiled agent.
_config_path = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
_runtime_config: dict[str, Any] = (
    (yaml.safe_load(_config_path.read_text(encoding="utf-8")) or {}) if _config_path.exists() else {}
)

agent = MICEEventPlanningChecklistVendorBriefGenerationAgent(config={**_runtime_config, "llm": _llm})

_hitl_enabled = agent.config.get("hitl", {}).get("enabled", False)
_needs_checkpointer = agent.config.get("memory_enabled") or _hitl_enabled
agent.compile(checkpointer=MemorySaver() if _needs_checkpointer else None)
agent.provision_secrets(_secrets_provider)


class InvokeRequest(BaseModel):
    input: str
    session_id: str = ""


def _bearer_matches(supplied: str, expected: str) -> bool:
    """Constant-time bearer comparison that is safe for non-ASCII header input."""
    return secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode())


def _resolve_standalone_trust(
    current: TrustLevel, authorization: str, invoke_auth_token: str | None, internal_runner_token: str | None
) -> TrustLevel:
    """Authenticate standalone callers without allowing external-token elevation.

    STG_INTERNAL_RUNNER_TOKEN is a distinct, CI-generated deployment credential.
    It is considered only for an anonymous caller and maps exactly to INTERNAL;
    INVOKE_AUTH_TOKEN remains VERIFIED_EXTERNAL. Middleware-established trust is
    never changed.
    """
    if current is not TrustLevel.ANONYMOUS:
        return current
    if internal_runner_token and _bearer_matches(authorization, internal_runner_token):
        return TrustLevel.INTERNAL
    if invoke_auth_token and _bearer_matches(authorization, invoke_auth_token):
        return TrustLevel.VERIFIED_EXTERNAL
    if internal_runner_token or invoke_auth_token:
        raise HTTPException(status_code=401, detail="Token is invalid or expired.")
    return TrustLevel.ANONYMOUS


@app.post("/invoke")
async def invoke(req: InvokeRequest, request: Request) -> dict[str, Any]:
    trust = _resolve_standalone_trust(
        getattr(request.state, "trust_level", TrustLevel.ANONYMOUS),
        request.headers.get("authorization", ""),
        os.environ.get("INVOKE_AUTH_TOKEN"),
        os.environ.get("STG_INTERNAL_RUNNER_TOKEN"),
    )
    ctx = InvocationContext(
        session_id=req.session_id or str(uuid4()),
        caller_trust_level=trust,
        caller_id=getattr(request.state, "caller_id", ""),
    )
    with bound_secrets(agent._secrets_provider):
        result: dict[str, Any] = agent.invoke(req.input, ctx=ctx)
        return result


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "MICEEventPlanningChecklistVendorBriefGenerationAgent"}
