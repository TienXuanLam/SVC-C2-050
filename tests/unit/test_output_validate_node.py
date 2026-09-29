# SVC-C2-050 — Unit Tests: OutputValidateNode (BL-54..BL-60)

from framework.schemas.trust_level import TrustLevel
from src.nodes.output_validate_node import DISCLAIMER, OutputValidateNode


def _state(**overrides) -> dict:
    state = {
        "mode": "full_generation",
        "event_type": "conference",
        "format": "in_person",
        "attendee_count": 150,
        "duration_days": 2,
        "event_name": "Annual Partner Summit",
        "checklist_template": {"event_type": "conference", "fallback": False, "phases": {"T-90": ["task 1"]}},
        "checklist_markdown": "## T-90 days\n- task 1 elaborated",
        "vendor_briefs_markdown": "## Venue\n- requirement",
        "timeline_markdown": "| Milestone | Date |\n|---|---|\n| Kickoff | T-90 |",
        "node_history": [],
        "error_log": [],
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "correlation_id": "test-corr",
        "session_id": "test-session",
        "thread_id": "test-thread",
        "trace_id": "",
        "caller_id": "",
        "hitl_allowed": True,
    }
    state.update(overrides)
    return state


class TestOutputValidateNode:
    def setup_method(self):
        self.node = OutputValidateNode()

    def test_disclaimer_always_present(self):
        """BL-54: the mandatory disclaimer is always attached."""
        result = self.node.execute(_state())
        assert result["status"] == "success"
        assert result["formatted_output"].endswith(DISCLAIMER.strip("\n"))

    def test_full_generation_mode_assembles_all_three_documents(self):
        """BL-55"""
        result = self.node.execute(_state())
        assert "Planning Checklist" in result["formatted_output"]
        assert "Vendor Briefs" in result["formatted_output"]
        assert "Master Timeline" in result["formatted_output"]

    def test_template_only_mode_renders_kb_structure_without_llm(self):
        """BL-56: template_only mode renders checklist_template directly — no LLM content needed."""
        result = self.node.execute(
            _state(mode="template_only", checklist_markdown="", vendor_briefs_markdown="", timeline_markdown="")
        )
        assert result["status"] == "success"
        assert "template_only mode" in result["formatted_output"]
        assert "task 1" in result["formatted_output"]

    def test_template_only_mode_discloses_fallback(self):
        """BL-57: an event_type that used the KB fallback structure is disclosed in the output."""
        result = self.node.execute(
            _state(
                mode="template_only",
                checklist_markdown="",
                vendor_briefs_markdown="",
                timeline_markdown="",
                checklist_template={"event_type": "family_reunion", "fallback": True, "phases": {"T-90": ["task"]}},
            )
        )
        assert "generic fallback" in result["formatted_output"]

    def test_s3_rejects_unsafe_output(self):
        """BL-58: invoked via __call__() — the real S-1->S-2->execute->S-3
        lifecycle, not execute() + the hook called directly (which bypasses
        _security_gate_output(), the @final method that actually decides
        whether the RuntimeError is caught and turned into status=error).
        Also proves no formatted_output leaks into the blocked result."""
        state = _state(vendor_briefs_markdown="Vendor: Grand Convention Services Co., Ltd.")
        result = self.node(state)  # __call__ — full S-1..S-4 lifecycle
        assert result["status"] == "error"
        assert "formatted_output" not in result
        assert "final_document_markdown" not in result

    def test_trust_gate_rejects_anonymous_caller(self):
        """BL-59/TC-08: OutputValidateNode requires VERIFIED_EXTERNAL — must call
        via __call__() (not execute()) since the S-1 gate lives in __call__()."""
        state = _state(caller_trust_level=TrustLevel.ANONYMOUS.value)
        result = self.node(state)
        assert result["status"] == "error"

    def test_trust_gate_allows_verified_external_caller(self):
        """BL-60"""
        state = _state(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL.value)
        result = self.node(state)
        assert result["status"] == "success"
