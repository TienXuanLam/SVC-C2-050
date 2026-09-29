# SVC-C2-050 — Unit Tests: MiceChecklistKBService (BL-17..BL-21)

from src.services.mice_checklist_kb_service import MiceChecklistKBService


class TestMiceChecklistKBService:
    def setup_method(self):
        self.kb = MiceChecklistKBService()

    def test_known_event_type_is_not_fallback(self):
        """BL-17"""
        result = self.kb.select_template("conference", "in_person")
        assert result["fallback"] is False
        assert result["event_type"] == "conference"
        assert result["phases"]["T-90"]  # non-empty

    def test_all_five_named_event_types_resolve(self):
        """BL-18: all 5 event types explicitly named in the proposal have dedicated KB entries."""
        for event_type in ("conference", "agm", "incentive", "product_launch", "exhibition"):
            result = self.kb.select_template(event_type, "in_person")
            assert result["fallback"] is False, f"{event_type} should not fall back"

    def test_unknown_event_type_falls_back(self):
        """BL-19: an unrecognized event_type degrades to the generic fallback, not a crash."""
        result = self.kb.select_template("family_reunion", "in_person")
        assert result["fallback"] is True
        assert result["phases"]["T-90"]  # fallback structure still has content

    def test_all_six_phases_present(self):
        """BL-20"""
        result = self.kb.select_template("conference", "in_person")
        assert set(result["phases"].keys()) == {"T-90", "T-60", "T-30", "T-7", "event_day", "post_event"}

    def test_hybrid_format_adds_addon_tasks(self):
        """BL-21: hybrid format merges streaming/remote-participant tasks into the base structure."""
        in_person = self.kb.select_template("conference", "in_person")
        hybrid = self.kb.select_template("conference", "hybrid")
        assert len(hybrid["phases"]["T-30"]) > len(in_person["phases"]["T-30"])
        assert len(hybrid["phases"]["event_day"]) > len(in_person["phases"]["event_day"])
