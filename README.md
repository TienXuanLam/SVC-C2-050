# SVC-C2-050 — MICEEventPlanningChecklistVendorBriefGenerationAgent

> **Category**: Cat 2 (multi-step domain workflow — orchestrates a specific job-to-be-done)
> **Industry**: SVC
> **Pattern reference**: DocGenerationAgent (label only — inherits `AgentBaseGraph` L1-direct,
> per the source proposal §1; not an inheritance base)
> **Status**: Draft

## Overview

Receives structured MICE (Meetings, Incentives, Conferences, Exhibitions) event parameters
(type, scale, duration, venue type, format, special requirements — attendee names, company
names, and budget figures rejected at S-1) and produces a management-ready planning document
set: a phase-by-phase checklist (T-90/60/30/7 days, event-day, post-event), vendor-specific
briefs (venue, catering, AV/tech, transport, accommodation), and a master timeline with vendor
deadline dependencies.

## Known Limitations

- **The MICE checklist KB is illustrative, not sourced Japan Tourism Agency/JNTO data.**
  `src/services/data/mice_checklist_templates.json` was authored by the implementing engineer to
  make the pipeline runnable — it is NOT a sourced or versioned extract of actual Japan Tourism
  Agency or JNTO MICE guideline material, despite the source proposal listing those as the
  intended KB source. Every task line is explicitly marked
  `[Illustrative example, not sourced Tourism Agency/JNTO text]`. See
  `src/services/data/README.md` and `docs/02_design.md`. Every deploying company must review
  generated checklists against actual current guidance before relying on them for real event
  planning.
- **Sensitive-data detection (attendee names, company names, budget figures) is a
  regex/keyword heuristic, not a certified NER/PII detector.**
  `src/services/sensitive_event_data_scan.py` catches a known set of forbidden field names,
  currency-amount patterns, common legal-entity suffixes (Inc./Corp./Co., Ltd./LLC/K.K./Group),
  and cue-worded name patterns — it will miss unconventional formats (e.g. a Japanese company
  name without a recognized suffix) and can false-positive on unrelated text that happens to
  match a pattern.
- **Prompt-injection detection is a regex/keyword heuristic, not a semantic classifier.**
  `src/services/prompt_injection_scan.py` matches known injection phrasings ("ignore previous
  instructions", "you are now", etc.) — it will miss novel phrasings designed to evade these
  specific patterns.
- **`template_only` mode is an implementation addition, not in the source proposal.** The
  source proposal's workflow always ends in an LLM report-drafting chain, with no LLM-free path
  — see `docs/02_design.md` "template_only mode" for why this was added and its rationale.

## Why This Template Exists

This template is **one production unit of the Agent 1000 line** — not a standalone
deliverable. The project goal is to make us *capable of producing* 1,000+ templates
per FY26 September capacity. That capability is what unlocks AGENTIC STAR as the
global de facto platform for enterprise agent development.

Of every design decision in this template, ask:

> "Does this make the next template faster, or only this one better?"

If your answer is the latter, reconsider — generalize at Level 2, or refactor the
pattern. A template that is technically beautiful but cannot be replicated quickly
across industries fails the mission. See the project charter for the three-layer
vision and full purpose context.

## Requirements

- Python 3.11+
- Optional: an `ANTHROPIC_API_KEY` secret to enable `full_generation` mode
  (LLM-drafted checklist, vendor briefs, and timeline)

### Behaviour without the platform

Without `ANTHROPIC_API_KEY` configured, the standalone server still boots and
`template_only` mode (`mode: "template_only"` in the request payload) reaches
`status=success` fully deterministically — it renders the KB-selected
checklist structure directly, with no LLM call. `full_generation` mode
requires a configured LLM and fails closed with a clear "LLM client not
configured" error otherwise.

## Quick Start

```bash
python3.11 -m venv .venv
source .venv/bin/activate  # or .venv/Scripts/activate on Windows
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Project Structure

```
config/
  agent.yaml          # AgentRegistry manifest
  config.yaml         # runtime parameters (kb_path, system_prompt)
deploy/
  invoke_payload.json # sample /invoke payload
  local-stg.yml       # local STG-equivalent deploy config
src/
  api/server.py       # standalone HTTP entry point
  graph/graph.py       # outer AgentBaseGraph + GraphNode wiring
  graph/domain_workflow_graph.py  # inner domain workflow graph
  nodes/               # outer pre_process / post_process nodes
  schemas/state.py     # flat TypedDict state
  services/            # pure domain logic (KB lookup, scans, LLM helper)
tests/
  unit/                # per-node/per-service unit tests
  integration/          # full outer+inner graph integration tests
  proof_of_boundary/   # framework-contract boundary tests
docs/
  02_design.md         # design specification
  03_test_spec.md      # test specification
cli.py                 # Marketplace Pod entrypoint
```

## Customising

- `config/config.yaml`: `max_retry`, `memory_enabled`, `timeout_s`, `kb_path`
  (override the bundled illustrative KB dataset), `system_prompt` (override
  the default LLM instructions).
- `config/agent.yaml`'s `requires.secrets`/`requires.extras`: adjust if the
  LLM provider changes.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This is a template under active development within the Agent 1000 line. It is
provided as-is, with no warranty, and may change without notice.
