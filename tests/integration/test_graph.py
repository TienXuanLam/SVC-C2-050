# SVC-C2-050 — Integration Tests: full outer graph (BL-61..BL-68)

import json

import pytest
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from shared.secrets.inmemory_provider import InMemoryProvider

from src.graph.domain_workflow_graph import MiceEventPlanningGraph
from src.graph.graph import MICEEventPlanningChecklistVendorBriefGenerationAgent, MiceEventPlanningGraphNode
from src.nodes.output_validate_node import DISCLAIMER


def _verified_ctx() -> InvocationContext:
    # pre_process / post_process require VERIFIED_EXTERNAL (docs/02_design.md S-1)
    return InvocationContext(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL)


class FakeLLM:
    """Matches shared.services.llm.base_llm.BaseLLM.complete() — takes a
    message list, returns the canonical {"content": ..., "tool_calls": [],
    "model": ...} dict. Records every messages list it was called with, so
    tests can assert on prompt content (e.g. Config Surface fields)."""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def complete(self, messages: list) -> dict:
        self.calls.append(messages)
        return {"content": "## Draft content\nGenerated section.", "tool_calls": [], "model": "fake"}


@pytest.fixture
def agent():
    a = MICEEventPlanningChecklistVendorBriefGenerationAgent(config={"llm": FakeLLM(), "max_retry": 1})
    a.compile()
    return a


@pytest.fixture
def secrets():
    return InMemoryProvider({})


def _payload(mode: str = "full_generation", event_type: str = "conference") -> str:
    return json.dumps(
        {
            "mode": mode,
            "event_type": event_type,
            "attendee_count": 150,
            "duration_days": 2,
            "venue_type": "convention_center",
            "format": "in_person",
            "event_name": "Annual Partner Summit",
            "special_requirements": "Wheelchair-accessible seating",
        }
    )


def test_full_generation_mode(agent, secrets):
    """BL-61: full_generation mode produces a complete document set with disclaimer."""
    with bound_secrets(secrets):
        result = agent.invoke(_payload("full_generation"), ctx=_verified_ctx())

    assert result["status"] == "success"
    assert "Planning Checklist" in result["output"]
    assert "Vendor Briefs" in result["output"]
    assert "Master Timeline" in result["output"]
    assert DISCLAIMER.strip("\n") in result["output"]


def test_template_only_mode(agent, secrets):
    """BL-62: template_only mode skips all 3 LLM steps and renders the KB structure directly."""
    with bound_secrets(secrets):
        result = agent.invoke(_payload("template_only"), ctx=_verified_ctx())

    assert result["status"] == "success"
    assert "template_only mode" in result["output"]


def test_invalid_input_returns_error(agent, secrets):
    with bound_secrets(secrets):
        result = agent.invoke("not valid json", ctx=_verified_ctx())

    assert result["status"] == "error"


def test_fractional_attendee_count_rejected_end_to_end(agent, secrets):
    """eng-moderator (MEDIUM): a fractional attendee_count must be rejected
    as a controlled validation error through the FULL compiled outer
    graph, before it reaches KB selection or any downstream generation
    node — proving int(150.5) == 150 silent truncation is fixed
    end-to-end, not just at the isolated node level."""
    payload = json.dumps(
        {
            "mode": "full_generation",
            "event_type": "conference",
            "attendee_count": 150.5,
            "duration_days": 2,
            "venue_type": "convention_center",
            "format": "in_person",
            "event_name": "Annual Partner Summit",
        }
    )
    with bound_secrets(secrets):
        result = agent.invoke(payload, ctx=_verified_ctx())

    assert result["status"] == "error"
    assert result["output"] is None


class UnsafeFakeLLM:
    """Simulates an LLM that leaks an apparent company name — the scenario
    S-3 exists to catch (LLM output is not proposal-guaranteed clean, even
    though upstream data never contained any — S-1/S-2 already rejected it)."""

    def complete(self, messages: list) -> dict:
        return {"content": "Vendor: Grand Convention Services Co., Ltd.", "tool_calls": [], "model": "fake-unsafe"}


def test_full_pipeline_blocks_unsafe_generated_content(secrets):
    """End-to-end: an LLM that leaks an apparent company name must not reach
    the caller as a successful document set. Complements the
    OutputValidateNode-only unit test with the full outer-graph lifecycle."""
    a = MICEEventPlanningChecklistVendorBriefGenerationAgent(config={"llm": UnsafeFakeLLM(), "max_retry": 1})
    a.compile()
    with bound_secrets(secrets):
        result = a.invoke(_payload("full_generation"), ctx=_verified_ctx())

    assert result["status"] == "error"
    assert result["output"] is None


def test_inner_graph_template_only_skips_llm_nodes(secrets):
    """Regression test: the outer agent's node_history only ever shows the 4
    outer nodes (InitializeNode/.../FinalizeNode) — it cannot see which inner
    nodes ran, so it can't catch a routing bug where template_only silently
    falls through to the LLM nodes anyway. Assert directly on the inner
    graph's own node_history instead (regression-tests a real
    langgraph==1.1.10 bound-method routing bug regression test)."""
    inner = MiceEventPlanningGraph(config={"llm": None})
    inner.compile()
    validated_input = json.dumps(
        {
            "mode": "template_only",
            "event_type": "conference",
            "attendee_count": 150,
            "duration_days": 2,
            "venue_type": "hotel",
            "format": "in_person",
            "event_name": "Summit",
        }
    )
    with bound_secrets(secrets):
        result = inner.invoke(validated_input, ctx=_verified_ctx())

    assert result["node_history"] == ["ChecklistTemplateSelectNode"]
    assert result["status"] == "success"  # no LLM needed for this mode


def test_inner_graph_full_generation_runs_all_four_nodes(secrets):
    inner = MiceEventPlanningGraph(config={"llm": FakeLLM()})
    inner.compile()
    validated_input = json.dumps(
        {
            "mode": "full_generation",
            "event_type": "conference",
            "attendee_count": 150,
            "duration_days": 2,
            "venue_type": "hotel",
            "format": "in_person",
            "event_name": "Summit",
        }
    )
    with bound_secrets(secrets):
        result = inner.invoke(validated_input, ctx=_verified_ctx())

    assert result["node_history"] == [
        "ChecklistTemplateSelectNode",
        "ChecklistGenerateNode",
        "VendorBriefDraftNode",
        "TimelineGenerateNode",
    ]
    assert result["status"] == "success"


def test_config_surface_reaches_llm_nodes(tmp_path, secrets):
    """Config Surface (proposal §10): kb_path / system_prompt must actually
    reach the running nodes, not just exist as unread config.yaml keys."""
    custom_kb = tmp_path / "custom_kb.json"
    custom_kb.write_text(
        json.dumps(
            {
                "event_types": {
                    "conference": {
                        "T-90": ["Custom KB task"],
                        "T-60": [],
                        "T-30": [],
                        "T-7": [],
                        "event_day": [],
                        "post_event": [],
                    },
                    "other": {"T-90": [], "T-60": [], "T-30": [], "T-7": [], "event_day": [], "post_event": []},
                },
                "hybrid_addon_tasks": {},
            }
        ),
        encoding="utf-8",
    )

    fake_llm = FakeLLM()
    inner = MiceEventPlanningGraph(
        config={"llm": fake_llm, "kb_path": str(custom_kb), "system_prompt": "TEST-SYSTEM-PROMPT"}
    )
    inner.compile()
    validated_input = json.dumps(
        {
            "mode": "full_generation",
            "event_type": "conference",
            "attendee_count": 150,
            "duration_days": 2,
            "venue_type": "hotel",
            "format": "in_person",
            "event_name": "Summit",
        }
    )
    with bound_secrets(secrets):
        result = inner.invoke(validated_input, ctx=_verified_ctx())

    assert result["status"] == "success"
    # kb_path: the custom KB entry (not the bundled default) was retrieved
    assert result["output"]["checklist_template"]["phases"]["T-90"] == ["Custom KB task"]
    # system_prompt: threaded as the system-role message
    all_system_prompts = " ".join(m["content"] for call in fake_llm.calls for m in call if m["role"] == "system")
    assert "TEST-SYSTEM-PROMPT" in all_system_prompts


def test_graph_node_trust_gate_lifecycle(secrets):
    """MiceEventPlanningGraphNode (a GraphNode) lives in src/graph/graph.py,
    not src/nodes/ — PB-6's discovery only scans src/nodes/, so this node's
    S-1/S-4 __call__ lifecycle has no other coverage. Exercised directly via
    __call__(), not only indirectly through the outer agent."""
    node = MiceEventPlanningGraphNode(llm=None)

    anonymous_state = {
        "caller_trust_level": TrustLevel.ANONYMOUS.value,
        "correlation_id": "x",
        "session_id": "x",
        "thread_id": "x",
        "trace_id": "",
        "hitl_allowed": True,
        "node_history": [],
        "error_log": [],
    }
    denied = node(anonymous_state)
    assert denied["status"] == "error"

    validated_input = json.dumps(
        {
            "mode": "template_only",
            "event_type": "conference",
            "attendee_count": 150,
            "duration_days": 2,
            "venue_type": "hotel",
            "format": "in_person",
            "event_name": "Summit",
        }
    )
    verified_state = {
        **anonymous_state,
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "validated_input": validated_input,
    }
    with bound_secrets(secrets):
        allowed = node(verified_state)
    assert allowed["status"] == "success"
    assert "MiceEventPlanningGraphNode" in allowed["node_history"]
