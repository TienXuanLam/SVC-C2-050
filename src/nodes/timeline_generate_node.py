"""AgentCore Platform v1.0"""

# Inner domain workflow node (docs/02_design.md — proposal step 5:
# TimelineGenerate). LLM-generates a master timeline with key milestones and
# vendor deadline dependencies, from the checklist structure and vendor
# brief categories already established upstream.

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.llm_helper import complete_text


def _build_prompt(state: AgentState) -> str:
    template = state.get("checklist_template", {})
    phases = template.get("phases", {})
    phase_names = ", ".join(phases.keys())
    return (
        f"Event type: {state.get('event_type', '')} | Format: {state.get('format', '')} | "
        f"Duration: {state.get('duration_days', 0)} day(s)\n"
        f"Checklist phases already established: {phase_names}\n\n"
        "Generate a master timeline in Markdown (a table or ordered list) that consolidates "
        "the key milestones from each phase above into a single chronological view, and "
        "explicitly calls out vendor deadline dependencies (e.g. 'catering headcount must be "
        "confirmed before the venue final walkthrough'). Do not invent attendee names, company "
        "names, or budget figures, and do not invent phases beyond the ones listed above."
    )


class TimelineGenerateNode(FunctionNode):
    """LLM-generate the master timeline with vendor deadline dependencies."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: Any | None = None, system_prompt: str | None = None) -> None:
        super().__init__()
        self._llm = llm
        self._system_prompt = system_prompt

    def execute(self, state: AgentState) -> dict[str, Any]:
        if self._llm is None:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["TimelineGenerateNode: LLM client not configured"],
            }

        prompt = _build_prompt(state)
        try:
            raw_response = complete_text(self._llm, prompt, self._system_prompt)
        except Exception as exc:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"TimelineGenerateNode: LLM request failed: {exc}"],
            }

        if not raw_response.strip():
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["TimelineGenerateNode: LLM returned empty content"],
            }

        emit_trace_event("timeline_generated", {"event_type": state.get("event_type", "")}, state)

        return {
            "timeline_markdown": raw_response,
            "status": AgentStatus.SUCCESS.value,
        }
