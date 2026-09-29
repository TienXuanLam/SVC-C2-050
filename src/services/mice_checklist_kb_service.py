"""AgentCore Platform v1.0"""

# Pure domain logic — no LLM, no agenticstar/framework imports. Selects the
# checklist phase structure for an event type (+ format), from the bundled
# illustrative KB (src/services/data/mice_checklist_templates.json — see
# src/services/data/README.md for the "not sourced Tourism Agency/JNTO text"
# disclosure). Deterministic and testable in isolation.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_KB_PATH = Path(__file__).parent / "data" / "mice_checklist_templates.json"
_PHASES = ("T-90", "T-60", "T-30", "T-7", "event_day", "post_event")


class MiceChecklistKBService:
    """Loads the MICE checklist KB and selects a phase structure per event type."""

    def __init__(self, kb_path: str | None = None) -> None:
        path = Path(kb_path) if kb_path else _DEFAULT_KB_PATH
        data = json.loads(path.read_text(encoding="utf-8"))
        self._event_types: dict[str, dict[str, list[str]]] = data.get("event_types", {})
        self._hybrid_addon: dict[str, list[str]] = data.get("hybrid_addon_tasks", {})

    def select_template(self, event_type: str, event_format: str) -> dict[str, Any]:
        """Return {"event_type", "fallback", "phases": {phase: [tasks]}}.

        fallback=True means event_type had no dedicated KB entry and the
        generic "other" structure was used instead (proposal §11 risk #2
        mitigation — a typo/unknown event type must not crash or return
        nothing, it degrades to a usable generic checklist).
        """
        fallback = event_type not in self._event_types
        structure = self._event_types.get(event_type, self._event_types.get("other", {}))

        phases: dict[str, list[str]] = {phase: list(structure.get(phase, [])) for phase in _PHASES}

        if event_format == "hybrid":
            for phase, addon_tasks in self._hybrid_addon.items():
                if phase in phases:
                    phases[phase] = phases[phase] + list(addon_tasks)

        return {"event_type": event_type, "fallback": fallback, "phases": phases}
