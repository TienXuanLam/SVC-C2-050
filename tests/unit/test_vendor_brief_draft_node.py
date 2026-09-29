# SVC-C2-050 — Unit Tests: VendorBriefDraftNode (BL-46..BL-49)

from src.nodes.vendor_brief_draft_node import VendorBriefDraftNode


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
        "format": "hybrid",
        "attendee_count": 150,
        "duration_days": 2,
        "venue_type": "hotel",
        "event_name": "Summit",
        "special_requirements": "",
        "notes": "",
        "node_history": [],
        "error_log": [],
    }


class TestVendorBriefDraftNode:
    def test_success_path(self):
        """BL-46"""
        node = VendorBriefDraftNode(llm=FakeLLM("## Venue\n- requirement"))
        result = node.execute(_state())
        assert result["status"] == "success"
        assert "Venue" in result["vendor_briefs_markdown"]

    def test_llm_not_configured(self):
        """BL-47"""
        node = VendorBriefDraftNode(llm=None)
        result = node.execute(_state())
        assert result["status"] == "error"

    def test_llm_provider_exception_fails_closed(self):
        """BL-48"""
        node = VendorBriefDraftNode(llm=RaisingLLM())
        result = node.execute(_state())
        assert result["status"] == "error"

    def test_llm_empty_content_is_an_error(self):
        """BL-49"""
        node = VendorBriefDraftNode(llm=FakeLLM(""))
        result = node.execute(_state())
        assert result["status"] == "error"
