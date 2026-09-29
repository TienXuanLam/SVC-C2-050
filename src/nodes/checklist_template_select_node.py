"""AgentCore Platform v1.0"""

# Inner domain workflow node (docs/02_design.md — proposal step 2:
# ChecklistTemplateSelect). First node of the inner graph: BaseGraph.invoke()
# only forwards a single string (the outer node's extract_input() return
# value, a JSON string built by EventParamIngestNode) — this node re-parses
# it and rehydrates the individual fields into inner state for downstream
# nodes. Deterministic KB lookup — NO LLM.

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.mice_checklist_kb_service import MiceChecklistKBService


class ChecklistTemplateSelectNode(FunctionNode):
    """Parse the forwarded request and select the applicable checklist structure."""

    # S-1: matches config/agent.yaml's agent-level required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, kb_service: MiceChecklistKBService | None = None) -> None:
        super().__init__()
        self._kb = kb_service or MiceChecklistKBService()

    def execute(self, state: AgentState) -> dict[str, Any]:
        raw = state.get("user_input", "") or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}

        event_type = payload.get("event_type", "")
        event_format = payload.get("format", "in_person")

        checklist_template = self._kb.select_template(event_type, event_format)

        emit_trace_event(
            "checklist_template_selected",
            {"event_type": event_type, "fallback": checklist_template["fallback"], "format": event_format},
            state,
        )

        return {
            "mode": payload.get("mode", "full_generation"),
            "event_type": event_type,
            "attendee_count": payload.get("attendee_count", 0),
            "duration_days": payload.get("duration_days", 0),
            "venue_type": payload.get("venue_type", ""),
            "format": event_format,
            "event_name": payload.get("event_name", ""),
            "special_requirements": payload.get("special_requirements", ""),
            "notes": payload.get("notes", ""),
            "checklist_template": checklist_template,
            "status": AgentStatus.SUCCESS.value,
        }
