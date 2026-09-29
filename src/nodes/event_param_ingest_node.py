"""AgentCore Platform v1.0"""

# Outer pre_process node (docs/02_design.md — proposal step 1:
# EventParamIngest). Parses the structured event-parameter JSON payload,
# validates it, and normalizes it into validated_input (a JSON string) for
# the inner domain workflow graph (GraphNode.extract_input() can only
# forward a single string — see docs/02_design.md State Definition note).

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.prompt_injection_scan import contains_prompt_injection
from src.services.sensitive_event_data_scan import contains_sensitive_event_data

_VALID_MODES = {"full_generation", "template_only"}
_VALID_FORMATS = {"in_person", "hybrid"}
_REQUIRED_FIELDS = ("event_type", "attendee_count", "duration_days", "venue_type", "format", "event_name")

_MIN_ATTENDEE_COUNT = 1
_MAX_ATTENDEE_COUNT = 100_000
_MIN_DURATION_DAYS = 1
_MAX_DURATION_DAYS = 30
_MAX_SHORT_FIELD_LEN = 200
_MAX_FREE_TEXT_LEN = 2000


class EventParamIngestNode(FunctionNode):
    """Validate and normalize the incoming MICE event planning request."""

    # S-1: corporate secretariat/event-staff caller only — not anonymous public.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: AgentState) -> AgentState:
        """S-1/S-2 domain checks (proposal §3 — both MANDATORY):
        reject attendee names/company names/budget figures, and reject
        prompt-injection patterns in the free-text fields, before any of the
        3 downstream LLM nodes can see the payload."""
        raw = state.get("user_input", "") or ""
        rejection: str | None = None
        if contains_sensitive_event_data(raw):
            rejection = "apparent attendee name, company name, or budget figure detected"
        elif contains_prompt_injection(raw):
            rejection = "apparent prompt-injection pattern detected in free-text field"

        if rejection:
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = list(state.get("error_log", [])) + [
                f"EventParamIngestNode: input rejected — {rejection}"
            ]
        return state

    @staticmethod
    def _parse_and_validate(raw: str) -> tuple[dict[str, Any] | None, str | None]:
        """Return (normalized_payload, None) on success, or (None, error_message)."""
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return None, "user_input is not valid JSON"

        missing = [f for f in _REQUIRED_FIELDS if f not in payload]
        if missing:
            return None, f"missing required field(s): {missing}"

        mode = payload.get("mode", "full_generation")
        if mode not in _VALID_MODES:
            return None, f"invalid mode {mode!r}"

        event_format = payload["format"]
        if event_format not in _VALID_FORMATS:
            return None, f"invalid format {event_format!r} — must be one of {sorted(_VALID_FORMATS)}"

        event_type = payload["event_type"]
        if not isinstance(event_type, str) or not event_type.strip():
            return None, "event_type must be a non-empty string"
        if len(event_type) > _MAX_SHORT_FIELD_LEN:
            return None, f"event_type exceeds max length ({_MAX_SHORT_FIELD_LEN} chars)"

        venue_type = payload["venue_type"]
        if not isinstance(venue_type, str) or not venue_type.strip():
            return None, "venue_type must be a non-empty string"
        if len(venue_type) > _MAX_SHORT_FIELD_LEN:
            return None, f"venue_type exceeds max length ({_MAX_SHORT_FIELD_LEN} chars)"

        attendee_count_raw = payload["attendee_count"]
        if isinstance(attendee_count_raw, bool):  # bool is an int subclass — reject explicitly
            return None, "attendee_count must be an integer, not a boolean"
        if isinstance(attendee_count_raw, float) and not attendee_count_raw.is_integer():
            # eng-moderator (MEDIUM): int(12.7) == 12 silently truncates a
            # fractional value instead of rejecting it — a caller-supplied
            # attendee_count of "150.5" was previously accepted and
            # silently rounded down to 150, corrupting the input without
            # any error surfaced.
            return None, "attendee_count must be a whole number, not a fractional value"
        if not isinstance(attendee_count_raw, (int, float)):
            return None, "attendee_count must be an integer"
        attendee_count = int(attendee_count_raw)
        if not (_MIN_ATTENDEE_COUNT <= attendee_count <= _MAX_ATTENDEE_COUNT):
            return None, f"attendee_count must be between {_MIN_ATTENDEE_COUNT} and {_MAX_ATTENDEE_COUNT}"

        duration_raw = payload["duration_days"]
        if isinstance(duration_raw, bool):
            return None, "duration_days must be an integer, not a boolean"
        if isinstance(duration_raw, float) and not duration_raw.is_integer():
            return None, "duration_days must be a whole number, not a fractional value"
        if not isinstance(duration_raw, (int, float)):
            return None, "duration_days must be an integer"
        duration_days = int(duration_raw)
        if not (_MIN_DURATION_DAYS <= duration_days <= _MAX_DURATION_DAYS):
            return None, f"duration_days must be between {_MIN_DURATION_DAYS} and {_MAX_DURATION_DAYS}"

        event_name = payload["event_name"]
        if not isinstance(event_name, str) or not event_name.strip():
            return None, "event_name must be a non-empty string"
        if len(event_name) > _MAX_SHORT_FIELD_LEN:
            return None, f"event_name exceeds max length ({_MAX_SHORT_FIELD_LEN} chars)"

        for field in ("special_requirements", "notes"):
            value = payload.get(field, "")
            if not isinstance(value, str):
                return None, f"{field} must be a string"
            if len(value) > _MAX_FREE_TEXT_LEN:
                return None, f"{field} exceeds max length ({_MAX_FREE_TEXT_LEN} chars)"

        return {
            "mode": mode,
            "event_type": event_type,
            "attendee_count": attendee_count,
            "duration_days": duration_days,
            "venue_type": venue_type,
            "format": event_format,
            "event_name": event_name,
            "special_requirements": str(payload.get("special_requirements", "")),
            "notes": str(payload.get("notes", "")),
        }, None

    def execute(self, state: AgentState) -> dict[str, Any]:
        if state.get("status") == AgentStatus.ERROR.value:
            # Already rejected by the S-1/S-2 hook above.
            return {"status": AgentStatus.ERROR.value}

        normalized, error = self._parse_and_validate(state.get("user_input", "") or "")
        if error or normalized is None:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"EventParamIngestNode: {error}"],
            }

        emit_trace_event(
            "event_params_ingested",
            {"event_type": normalized["event_type"], "format": normalized["format"], "mode": normalized["mode"]},
            state,
        )

        return {
            **normalized,
            "validated_input": json.dumps(normalized),
            "status": AgentStatus.SUCCESS.value,
        }
