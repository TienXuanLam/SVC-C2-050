"""AgentCore Platform v1.0"""

# S-1/S-2 domain check (proposal §3): this template only accepts structured
# event parameters — never attendee names, company names, or budget figures.
# Two entry points, mirroring an earlier project's individual_identifier_scan.py:
#   contains_sensitive_event_data(raw_input)      — structured JSON input scan
#   contains_sensitive_event_data_text(text)       — free-text/LLM-output scan
#
# KNOWN LIMITATION (README.md): company-name and attendee-name detection are
# regex/keyword heuristics (common legal-entity suffixes, cue-word + name
# patterns), not a certified NER/PII detector — see docs/02_design.md.

from __future__ import annotations

import json
import re
from typing import Any

_FORBIDDEN_KEYS = frozenset(
    {
        "attendee_name",
        "attendee_names",
        "participant_name",
        "participant_names",
        "guest_name",
        "company_name",
        "organizer_company",
        "client_company",
        "budget",
        "budget_amount",
        "cost",
        "total_cost",
    }
)

# Currency amounts: symbol/word-adjacent numbers (¥1,200,000 / 5000 USD / 300万円 etc.)
_BUDGET_RE = re.compile(
    r"[¥$€£]\s?\d[\d,]*(\.\d+)?" r"|\b\d[\d,]*(\.\d+)?\s?(yen|円|usd|jpy|dollars?)\b",
    re.IGNORECASE,
)

# Common legal-entity suffixes following a capitalized name — a heuristic
# company-name detector, not exhaustive (English + Japanese K.K./Co., Ltd.).
# Trailing lookahead, not \b: several suffixes end in "." (a non-word char),
# and \b never matches between two non-word chars (e.g. "." followed by a
# space) — a trailing \b would silently never match "Inc." / "Ltd." at all.
_COMPANY_SUFFIX_RE = re.compile(
    r"\b[A-Z][\w&.,\-]*(\s[A-Z][\w&.,\-]*){0,3}\s"
    r"(Inc\.|Incorporated|Corp\.|Corporation|Co\.,?\s?Ltd\.|LLC|K\.K\.|Group)(?=\s|[.,]|$)"
)

# Cue-word + capitalized-name pattern for attendee/contact names (mirrors
# a cue-word approach used in an earlier project's student_name_scan.py — avoids false
# positives on bare capitalized headings).
_ATTENDEE_NAME_RE = re.compile(
    r"(?i:attendee|participant|guest|contact\s?person)[\s:]+([A-Z][a-z]+\s[A-Z][a-z]+|\[MASKED\])"
)


def _contains_sensitive_text(text: str) -> bool:
    text = text or ""
    return bool(_BUDGET_RE.search(text) or _COMPANY_SUFFIX_RE.search(text) or _ATTENDEE_NAME_RE.search(text))


def contains_sensitive_event_data(raw_input: str) -> bool:
    """Return True if raw_input (JSON text) appears to carry attendee names,
    company names, or budget figures — structural key check plus a free-text
    scan across every string value in the parsed payload."""
    if _contains_sensitive_text(raw_input):
        return True

    try:
        payload = json.loads(raw_input) if (raw_input or "").strip() else {}
    except json.JSONDecodeError:
        return False  # malformed JSON is the ingest node's execute()'s problem, not this scan's

    def _walk(value: Any) -> bool:
        if isinstance(value, dict):
            for key, val in value.items():
                if str(key).strip().lower() in _FORBIDDEN_KEYS:
                    return True
                if _walk(val):
                    return True
            return False
        if isinstance(value, list):
            return any(_walk(item) for item in value)
        if isinstance(value, str):
            return _contains_sensitive_text(value)
        return False

    return _walk(payload)


def contains_sensitive_event_data_text(text: str) -> bool:
    """S-3 defense-in-depth: scan LLM-generated prose for attendee names,
    company names, or budget figures leaking despite aggregated input."""
    return _contains_sensitive_text(text)
