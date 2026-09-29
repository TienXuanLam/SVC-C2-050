# SVC-C2-050 — Unit Tests: sensitive_event_data_scan (BL-08..BL-16)

import json

from src.services.sensitive_event_data_scan import (
    contains_sensitive_event_data,
    contains_sensitive_event_data_text,
)


class TestContainsSensitiveEventData:
    def test_clean_event_params_pass(self):
        """BL-08: normal structured event parameters are not flagged."""
        raw = json.dumps(
            {
                "event_type": "conference",
                "attendee_count": 150,
                "duration_days": 2,
                "venue_type": "convention_center",
                "format": "in_person",
                "event_name": "Annual Partner Summit",
                "special_requirements": "Wheelchair-accessible seating",
            }
        )
        assert contains_sensitive_event_data(raw) is False

    def test_forbidden_key_attendee_name_is_flagged(self):
        """BL-09"""
        raw = json.dumps({"event_type": "conference", "attendee_name": "Taro Yamada"})
        assert contains_sensitive_event_data(raw) is True

    def test_forbidden_key_budget_is_flagged(self):
        """BL-10"""
        raw = json.dumps({"event_type": "conference", "budget": 5000000})
        assert contains_sensitive_event_data(raw) is True

    def test_forbidden_key_nested_is_flagged(self):
        """BL-11: forbidden keys are caught even nested inside another object."""
        raw = json.dumps({"event_type": "conference", "extra": {"company_name": "Acme Corp"}})
        assert contains_sensitive_event_data(raw) is True

    def test_budget_figure_in_free_text_is_flagged(self):
        """BL-12: a currency amount embedded in a free-text field."""
        raw = json.dumps(
            {
                "event_type": "conference",
                "event_name": "Summit",
                "special_requirements": "Budget is capped at ¥3,000,000 for catering.",
            }
        )
        assert contains_sensitive_event_data(raw) is True

    def test_company_suffix_in_free_text_is_flagged(self):
        """BL-13: a company name with a legal-entity suffix in free text."""
        raw = json.dumps(
            {
                "event_type": "conference",
                "event_name": "Summit",
                "notes": "Coordinate with Acme Solutions Inc. for logistics.",
            }
        )
        assert contains_sensitive_event_data(raw) is True

    def test_attendee_name_cue_word_in_free_text_is_flagged(self):
        """BL-14"""
        raw = json.dumps(
            {
                "event_type": "conference",
                "event_name": "Summit",
                "notes": "Contact person: Hanako Sato for on-site coordination.",
            }
        )
        assert contains_sensitive_event_data(raw) is True

    def test_malformed_json_does_not_crash(self):
        """BL-15: malformed JSON without any flaggable free-text pattern returns False."""
        assert contains_sensitive_event_data("not json at all") is False

    def test_empty_input_is_clean(self):
        """BL-16"""
        assert contains_sensitive_event_data("") is False


class TestContainsSensitiveEventDataText:
    def test_clean_markdown_passes(self):
        text = "## Vendor Brief: Catering\nProvide vegetarian options for 150 attendees."
        assert contains_sensitive_event_data_text(text) is False

    def test_budget_figure_in_output_is_flagged(self):
        assert contains_sensitive_event_data_text("Estimated cost: $50,000 for AV equipment.") is True

    def test_company_suffix_in_output_is_flagged(self):
        assert contains_sensitive_event_data_text("Vendor: Grand Convention Services Co., Ltd.") is True
