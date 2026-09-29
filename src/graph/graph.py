"""AgentCore Platform v1.0"""

# SVC-C2-050 — Cat 2: AgentBaseGraph (outer, fixed 5-node backbone) + GraphNode
# in the `main` slot wrapping the inner domain workflow graph
# (src/graph/domain_workflow_graph.py). Proposal §4 lists 6 steps
# (EventParamIngest / ChecklistTemplateSelect / ChecklistGenerate /
# VendorBriefDraft / TimelineGenerate / OutputValidate) — more than
# AgentBaseGraph's 3 fixed slots, so the 4 middle steps are encapsulated in
# the inner graph, matching the current Cat 2 scaffold convention
# (src/examples/graph_cat2_sample.py).
#
# Do NOT override add_edges() on this outer graph — backbone wiring
# (initialize -> pre_process -> main -> {route} -> post_process -> finalize)
# belongs to AgentBaseGraph.

from typing import TYPE_CHECKING, Any, ClassVar

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from src.nodes.event_param_ingest_node import EventParamIngestNode
from src.nodes.output_validate_node import OutputValidateNode
from src.schemas.state import State

if TYPE_CHECKING:
    from src.graph.domain_workflow_graph import MiceEventPlanningGraph


class MiceEventPlanningGraphNode(GraphNode):
    """Wraps the inner domain workflow graph; assigned to the outer `main` slot."""

    # S-1: check_trust_level.py only scans direct FunctionNode subclasses, so
    # GraphNode subclasses default to ANONYMOUS silently unless declared here
    # explicitly. Matches config/agent.yaml's agent-level required_trust_level
    # and the other two outer nodes.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    error_strategy: ClassVar[str] = "propagate"  # fail fast — no silent partial document set
    propagate_hitl: ClassVar[bool] = False

    def __init__(
        self,
        llm: Any | None = None,
        kb_service: Any | None = None,
        kb_path: Any | None = None,
        system_prompt: str | None = None,
    ) -> None:
        super().__init__()
        self._llm = llm
        self._kb_service = kb_service
        self._kb_path = kb_path
        self._system_prompt = system_prompt

    def get_subgraph(self) -> "MiceEventPlanningGraph":
        from src.graph.domain_workflow_graph import MiceEventPlanningGraph

        return MiceEventPlanningGraph(
            config={
                "llm": self._llm,
                "kb_service": self._kb_service,
                "kb_path": self._kb_path,
                "system_prompt": self._system_prompt,
            }
        )

    def extract_input(self, state: AgentState) -> str:
        # validated_input is the normalized JSON string built by
        # EventParamIngestNode — the single string the inner BaseGraph.invoke()
        # boundary requires (docs/02_design.md).
        return str(state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        output = sub_result.get("output", {}) or {}
        return {
            "checklist_template": output.get("checklist_template", {}),
            "checklist_markdown": output.get("checklist_markdown", ""),
            "vendor_briefs_markdown": output.get("vendor_briefs_markdown", ""),
            "timeline_markdown": output.get("timeline_markdown", ""),
            "status": sub_result.get("status"),
        }


class MICEEventPlanningChecklistVendorBriefGenerationAgent(AgentBaseGraph):
    """SVC-C2-050 — MICE event planning checklist and vendor brief generation."""

    @property
    def name(self) -> str:
        return "MICEEventPlanningChecklistVendorBriefGenerationAgent"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode

        self._nodes["pre_process"] = EventParamIngestNode()
        self._nodes["main"] = MiceEventPlanningGraphNode(
            llm=self.config.get("llm"),
            kb_service=self.config.get("kb_service"),
            kb_path=self.config.get("kb_path"),
            system_prompt=self.config.get("system_prompt"),
        )
        self._nodes["post_process"] = OutputValidateNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.
