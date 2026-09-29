# SVC-C2-050 — Unit Tests: TimelineGenerateNode (BL-50..BL-53)

from src.nodes.timeline_generate_node import TimelineGenerateNode


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
        "duration_days": 2,
        "checklist_template": {"event_type": "conference", "fallback": False, "phases": {"T-90": ["task 1"]}},
        "node_history": [],
        "error_log": [],
    }


class TestTimelineGenerateNode:
    def test_success_path(self):
        """BL-50"""
        node = TimelineGenerateNode(llm=FakeLLM("| Milestone | Date |\n|---|---|\n| Kickoff | T-90 |"))
        result = node.execute(_state())
        assert result["status"] == "success"
        assert "Milestone" in result["timeline_markdown"]

    def test_llm_not_configured(self):
        """BL-51"""
        node = TimelineGenerateNode(llm=None)
        result = node.execute(_state())
        assert result["status"] == "error"

    def test_llm_provider_exception_fails_closed(self):
        """BL-52"""
        node = TimelineGenerateNode(llm=RaisingLLM())
        result = node.execute(_state())
        assert result["status"] == "error"

    def test_llm_empty_content_is_an_error(self):
        """BL-53"""
        node = TimelineGenerateNode(llm=FakeLLM(""))
        result = node.execute(_state())
        assert result["status"] == "error"
