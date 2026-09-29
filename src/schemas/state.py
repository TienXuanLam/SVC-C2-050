"""AgentCore Platform v1.0"""

# State fields are flat primitives / containers of primitives only (see
# sdk/concepts/state-and-schemas.md) — msgpack-checkpoint-safe. No attendee
# names, company names, or budget figures of any kind ever land here — only
# structured event parameters and generated document text (proposal §3).

from typing import Any

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """SVC-C2-050 — MICEEventPlanningChecklistVendorBriefGenerationAgent state.

    Only fields specific to this agent are declared below. Shared fields
    (user_input, status, session_id, node_history, error_log, hitl_*, etc.)
    are inherited from AgentState.
    """

    # --- pre_process (EventParamIngestNode) ---
    mode: str  # "full_generation" (LLM documents) | "template_only" (no LLM)
    event_type: str  # conference | agm | incentive | product_launch | exhibition | other
    attendee_count: int
    duration_days: int
    venue_type: str
    format: str  # "in_person" | "hybrid"
    event_name: str  # free text, sanitized (S-2 prompt-injection + sensitive-data scan)
    special_requirements: str  # free text, sanitized
    notes: str  # free text, sanitized (optional)

    # --- main (MiceEventPlanningGraphNode <- inner domain workflow graph) ---
    checklist_template: dict[str, Any]  # KB-selected phase structure
    checklist_markdown: str  # LLM-generated phase-by-phase checklist (empty in template_only)
    vendor_briefs_markdown: str  # LLM-generated vendor briefs (empty in template_only)
    timeline_markdown: str  # LLM-generated master timeline (empty in template_only)

    # --- post_process (OutputValidateNode) ---
    final_document_markdown: str
