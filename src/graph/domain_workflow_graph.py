"""AgentCore Platform v1.0"""

# SVC-C2-050 — inner domain workflow graph (Cat 2, see docs/02_design.md).
# Instantiated by MiceEventPlanningGraphNode.get_subgraph() in graph.py.
# Inherits BaseGraph directly — fully custom topology, not the
# pre_process/main/post_process backbone (that belongs to the outer graph).
#
# Pipeline (branches once, on mode):
#     START -> checklist_template_select -> {route: mode}
#                full_generation: -> checklist_generate -> vendor_brief_draft
#                                    -> timeline_generate -> END
#                template_only:   -> END directly (OutputValidateNode renders
#                                    the KB-selected checklist_template instead)

from typing import Any

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.checklist_generate_node import ChecklistGenerateNode
from src.nodes.checklist_template_select_node import ChecklistTemplateSelectNode
from src.nodes.timeline_generate_node import TimelineGenerateNode
from src.nodes.vendor_brief_draft_node import VendorBriefDraftNode
from src.schemas.state import State
from src.services.mice_checklist_kb_service import MiceChecklistKBService


class MiceEventPlanningGraph(BaseGraph):
    """Inner graph for the 3-LLM-step MICE document generation workflow."""

    @property
    def name(self) -> str:
        return "mice_event_planning_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        # llm / kb_path are optional at this layer — individual nodes handle
        # an absent dependency defensively (see e.g. ChecklistGenerateNode).
        pass

    def register_nodes(self) -> None:
        llm = self.config.get("llm")
        kb_service = self.config.get("kb_service") or MiceChecklistKBService(self.config.get("kb_path"))
        system_prompt = self.config.get("system_prompt")

        self._nodes["checklist_template_select"] = ChecklistTemplateSelectNode(kb_service)
        self._nodes["checklist_generate"] = ChecklistGenerateNode(llm, system_prompt)
        self._nodes["vendor_brief_draft"] = VendorBriefDraftNode(llm, system_prompt)
        self._nodes["timeline_generate"] = TimelineGenerateNode(llm, system_prompt)

    def add_edges(self) -> None:
        self._sg.add_edge(START, "checklist_template_select")
        # lambda wrapper, not a bare `self.route` reference: passing the bound
        # method directly to add_conditional_edges (langgraph==1.1.10) caused
        # BOTH conditional targets to fire regardless of the returned value in
        # an earlier project (reproduced with a minimal StateGraph outside that
        # class) — the lambda wrapper does not exhibit the bug.
        self._sg.add_conditional_edges(
            "checklist_template_select",
            lambda state: self.route(state),
            {"checklist_generate": "checklist_generate", END: END},
        )
        self._sg.add_edge("checklist_generate", "vendor_brief_draft")
        self._sg.add_edge("vendor_brief_draft", "timeline_generate")
        self._sg.add_edge("timeline_generate", END)

    def route(self, state: AgentState) -> str:
        """Conditional routing after checklist_template_select.

        template_only mode skips all 3 LLM narrative steps entirely —
        OutputValidateNode (outer post_process) renders checklist_template
        directly instead (docs/02_design.md).
        """
        if state.get("status") == AgentStatus.ERROR.value:
            return END
        return "checklist_generate" if state.get("mode") == "full_generation" else END

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "output": {
                "checklist_template": state.get("checklist_template", {}),
                "checklist_markdown": state.get("checklist_markdown", ""),
                "vendor_briefs_markdown": state.get("vendor_briefs_markdown", ""),
                "timeline_markdown": state.get("timeline_markdown", ""),
            },
            "status": state.get("status", AgentStatus.ERROR.value),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
