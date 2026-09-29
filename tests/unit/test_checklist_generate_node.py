# SVC-C2-050 — Unit Tests: ChecklistGenerateNode (BL-42..BL-45)

from src.nodes.checklist_generate_node import ChecklistGenerateNode


class FakeLLM:
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages: list) -> dict:
        return {"content": self._response, "tool_calls": [], "model": "fake"}


class RaisingLLM:
    def complete(self, messages: list) -> dict:
        raise ConnectionError("simulated provider outage")


def _state() -> dict:
    return {
        "event_type": "conference",
        "format": "in_person",
        "attendee_count": 150,
        "duration_days": 2,
        "venue_type": "hotel",
        "event_name": "Summit",
        "special_requirements": "",
        "checklist_template": {"event_type": "conference", "fallback": False, "phases": {"T-90": ["task 1"]}},
        "node_history": [],
        "error_log": [],
    }


class TestChecklistGenerateNode:
    def test_success_path(self):
        """BL-42"""
        node = ChecklistGenerateNode(llm=FakeLLM("## T-90 days\n- task 1 elaborated"))
        result = node.execute(_state())
        assert result["status"] == "success"
        assert "T-90" in result["checklist_markdown"]

    def test_llm_not_configured(self):
        """BL-43: no LLM injected -> ERROR, does not crash (PB-6 safety)."""
        node = ChecklistGenerateNode(llm=None)
        result = node.execute(_state())
        assert result["status"] == "error"

    def test_llm_provider_exception_fails_closed(self):
        """BL-44"""
        node = ChecklistGenerateNode(llm=RaisingLLM())
        result = node.execute(_state())
        assert result["status"] == "error"
        assert result["error_log"]

    def test_llm_empty_content_is_an_error(self):
        """BL-45"""
        node = ChecklistGenerateNode(llm=FakeLLM(""))
        result = node.execute(_state())
        assert result["status"] == "error"
