"""AgentCore Platform v1.0"""

# S-2 MANDATORY domain check (proposal §3 Security Requirements, §10 #5):
# "prompt injection prevention MANDATORY; sanitize free-text fields in event
# parameters (event name, special requirements, notes) before passing to LLM
# nodes; reject inputs containing instruction-like patterns". Applied by
# EventParamIngestNode._extra_security_gate_input() to event_name,
# special_requirements, and notes before any of the three downstream LLM
# nodes (ChecklistGenerateNode/VendorBriefDraftNode/TimelineGenerateNode) can
# see them.
#
# KNOWN LIMITATION (README.md): this is a regex/keyword heuristic against
# well-known prompt-injection phrasings, not a semantic or model-based
# injection classifier. It will miss novel phrasings and can false-positive
# on legitimate text that happens to match a pattern (e.g. a special
# requirement literally about "system" AV equipment) — see docs/02_design.md.

from __future__ import annotations

import re

_INJECTION_PATTERNS = re.compile(
    r"(?i:"
    r"ignore\s+(all\s+|any\s+)?(previous|prior|the\s+above)\s+instructions"
    r"|disregard\s+(all\s+|any\s+)?(previous|prior|the\s+above)"
    r"|new\s+instructions\s*:"
    r"|you\s+are\s+now\s+(a|an)\b"
    r"|act\s+as\s+(a|an)\s+\w+\s+(and|,)?\s*(ignore|forget|disregard)"
    r"|forget\s+(everything|all)\s+(you\s+)?(know|were\s+told)"
    r"|system\s*prompt"
    r"|\byou\s+must\s+now\s+"
    r")"
    r"|</?system>"
    r"|^\s*###\s*(system|instruction)",
    re.MULTILINE,
)


def contains_prompt_injection(text: str) -> bool:
    """Return True if text matches a known prompt-injection phrasing pattern."""
    return bool(_INJECTION_PATTERNS.search(text or ""))
