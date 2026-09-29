"""AgentCore Platform v1.0"""

# Outer post_process node (docs/02_design.md — proposal step 6:
# OutputValidate). Assembles the final document set and attaches the
# mandatory disclaimer (risk #1 mitigation — proposal §11). S-3 extra hook
# re-scans all generated text for apparent attendee names, company names, or
# budget figures before output leaves the node boundary — LLM output is not
# proposal-guaranteed clean, even though the upstream data never contained
# any (S-1/S-2 already rejected it at ingest).
#
# template_only mode (docs/02_design.md): none of the 3 LLM nodes ran, so
# checklist_markdown/vendor_briefs_markdown/timeline_markdown are all empty —
# this node renders the KB-selected checklist_template directly instead of
# leaving a blank document.

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.sensitive_event_data_scan import contains_sensitive_event_data_text

DISCLAIMER = "\n\n---\n**⚠️ AI draft — event planner must verify with actual vendors before " "distribution.**"

_PHASE_LABELS = {
    "T-90": "T-90 days",
    "T-60": "T-60 days",
    "T-30": "T-30 days",
    "T-7": "T-7 days",
    "event_day": "Event day",
    "post_event": "Post-event",
}


def _render_template_only(state: AgentState) -> str:
    template = state.get("checklist_template", {})
    phases = template.get("phases", {})
    lines = [
        f"# MICE Planning Checklist Structure: {state.get('event_type', '')}",
        "*template_only mode — no LLM narrative; the KB-selected phase structure below is the " "raw result.*",
    ]
    if template.get("fallback"):
        lines.append("*⚠️ No dedicated KB entry for this event_type — the generic fallback structure " "was used.*")
    lines.append(
        "*Source: illustrative example data, not sourced Japan Tourism Agency/JNTO text — see "
        "README.md Known Limitations.*"
    )
    for phase, tasks in phases.items():
        lines += ["", f"## {_PHASE_LABELS.get(phase, phase)}"]
        lines += [f"- {task}" for task in tasks] if tasks else ["(no tasks)"]
    return "\n".join(lines)


def _render_full_document(state: AgentState) -> str:
    lines = [
        f"# MICE Event Planning Document Set: {state.get('event_name', '')}",
        f"**Type:** {state.get('event_type', '')} | **Format:** {state.get('format', '')} | "
        f"**Attendees:** {state.get('attendee_count', 0)} | "
        f"**Duration:** {state.get('duration_days', 0)} day(s)",
        "",
        "## Planning Checklist",
        state.get("checklist_markdown", ""),
        "",
        "## Vendor Briefs",
        state.get("vendor_briefs_markdown", ""),
        "",
        "## Master Timeline",
        state.get("timeline_markdown", ""),
    ]
    return "\n".join(lines)


class OutputValidateNode(FunctionNode):
    """Finalize the document set and attach the mandatory disclaimer."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        if contains_sensitive_event_data_text(str(result.get("final_document_markdown", ""))):
            raise RuntimeError(
                "OutputValidateNode: S-3 rejected output — apparent attendee name, company "
                "name, or budget figure detected in generated content"
            )
        return result

    def execute(self, state: AgentState) -> dict[str, Any]:
        if state.get("status") == AgentStatus.ERROR.value:
            return {"status": AgentStatus.ERROR.value}

        mode = state.get("mode", "full_generation")
        body = _render_template_only(state) if mode == "template_only" else _render_full_document(state)
        markdown = body + DISCLAIMER

        emit_trace_event("document_set_finalized", {"mode": mode, "event_type": state.get("event_type", "")}, state)

        return {
            "final_document_markdown": markdown,
            "formatted_output": markdown,
            "status": AgentStatus.SUCCESS.value,
        }
