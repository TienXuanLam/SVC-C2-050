# SVC-C2-050 — Unit Tests: ChecklistTemplateSelectNode (BL-39..BL-41)

import json

from src.nodes.checklist_template_select_node import ChecklistTemplateSelectNode


def _state(payload: dict) -> dict:
    return {"user_input": json.dumps(payload), "node_history": [], "error_log": []}


class TestChecklistTemplateSelectNode:
    def test_rehydrates_and_selects_template(self):
        """BL-39: forwarded JSON is re-parsed and the KB template selected."""
        node = ChecklistTemplateSelectNode()
        payload = {
            "mode": "full_generation",
            "event_type": "conference",
            "attendee_count": 150,
            "duration_days": 2,
            "venue_type": "hotel",
            "format": "in_person",
            "event_name": "Summit",
            "special_requirements": "",
            "notes": "",
        }
        result = node.execute(_state(payload))
        assert result["status"] == "success"
        assert result["checklist_template"]["event_type"] == "conference"
        assert result["checklist_template"]["fallback"] is False

    def test_unknown_event_type_falls_back_without_crash(self):
        """BL-40"""
        node = ChecklistTemplateSelectNode()
        payload = {
            "mode": "full_generation",
            "event_type": "family_reunion",
            "attendee_count": 20,
            "duration_days": 1,
            "venue_type": "park",
            "format": "in_person",
            "event_name": "Reunion",
            "special_requirements": "",
            "notes": "",
        }
        result = node.execute(_state(payload))
        assert result["status"] == "success"
        assert result["checklist_template"]["fallback"] is True

    def test_default_kb_service_used_when_none_injected(self):
        """BL-41: constructor with no kb_service builds the default one, no crash."""
        node = ChecklistTemplateSelectNode(kb_service=None)
        payload = {"mode": "full_generation", "event_type": "conference", "format": "in_person"}
        result = node.execute(_state(payload))
        assert result["status"] == "success"
