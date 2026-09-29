# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `MICEEventPlanningChecklistVendorBriefGenerationAgent`
- **L1 Base**: `AgentBaseGraph`
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible), `src/schemas/state.py`
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

Proposal (source proposal §4) lists six steps —
EventParamIngest, ChecklistTemplateSelect, ChecklistGenerate, VendorBriefDraft, TimelineGenerate,
OutputValidate — more than `AgentBaseGraph`'s three fixed slots (`pre_process` / `main` /
`post_process`). Per the current scaffold convention (`src/examples/graph_cat2_sample.py`), the
four middle steps are encapsulated in an inner `BaseGraph` wrapped by a `GraphNode` in the outer
`main` slot:

```
Outer graph (src/graph/graph.py):
    AgentBaseGraph — fixed backbone, add_edges() NOT overridden.
    pre_process  = EventParamIngestNode              (proposal step 1)
    main         = MiceEventPlanningGraphNode         (GraphNode wrapping the inner graph)
    post_process = OutputValidateNode                 (proposal step 6)

Inner graph (src/graph/domain_workflow_graph.py):
    MiceEventPlanningGraph(BaseGraph) — fully custom topology.
    checklist_template_select (step 2) -> {route: mode}
        full_generation: -> checklist_generate (step 3, LLM) -> vendor_brief_draft (step 4, LLM)
                          -> timeline_generate (step 5, LLM) -> END
        template_only:   -> END directly
```

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | — | — | InitializeNode (default) |
| pre_process | `EventParamIngestNode` — parse/validate event parameters, reject attendee/company/budget data and prompt-injection patterns (S-1/S-2) | `user_input` | event parameters, `validated_input` | FunctionNode |
| main | `MiceEventPlanningGraphNode` — wraps the inner 4-step graph | `validated_input` | `checklist_template`, `checklist_markdown`, `vendor_briefs_markdown`, `timeline_markdown` | GraphNode |
| ↳ checklist_template_select | KB lookup by event_type × format | `user_input` (forwarded JSON) | `checklist_template` | FunctionNode (inner) |
| ↳ checklist_generate | LLM-elaborate the KB structure into a full checklist (skipped in `template_only` mode) | `checklist_template` | `checklist_markdown` | FunctionNode (inner) |
| ↳ vendor_brief_draft | LLM-draft vendor-category briefs (skipped in `template_only` mode) | event parameters | `vendor_briefs_markdown` | FunctionNode (inner) |
| ↳ timeline_generate | LLM-generate master timeline (skipped in `template_only` mode) | `checklist_template` | `timeline_markdown` | FunctionNode (inner) |
| post_process | `OutputValidateNode` — assemble document set, attach disclaimer, render KB structure directly for `template_only`, S-3 re-scan | generated markdown or `checklist_template` | `final_document_markdown`, `formatted_output` | FunctionNode |
| finalize | response_metadata, total_time_ms | — | — | FinalizeNode (default) |

### Data Flow

```
START → initialize → pre_process → main → {route} → post_process → finalize → END
                                            ↓ (retry)
                                          pre_process
```

### `template_only` mode — not in the source proposal, added during implementation

The source proposal's workflow always ends in an LLM report-drafting chain (steps 3-5), with no
LLM-free path. That makes the pipeline impossible to exercise end-to-end (Stage ⑤ STG smoke test
/ CI `run-tests`) without a real `ANTHROPIC_API_KEY`. Mirroring an earlier project's
`deterministic_only` precedent, `EventParamIngestNode` accepts an optional `mode` field
(`"full_generation"` default, or `"template_only"`): in `template_only` mode the inner graph
routes straight from `checklist_template_select` to `END`, skipping all 3 LLM nodes entirely, and
`OutputValidateNode` renders the already-selected `checklist_template` KB structure directly
instead of an LLM narrative. This also addresses proposal §11 risk #3 ("response time and token
cost from generating full 8-12 document set at once ... implement section-split output mode") in
spirit, via mode splitting rather than granular per-document-type selection — see README.md Known
Limitations for the disclosed scope narrowing.

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `mode` | `str` | `"full_generation"` (LLM documents) or `"template_only"` (no LLM) | pre_process |
| `event_type` | `str` | conference / agm / incentive / product_launch / exhibition / other | pre_process |
| `attendee_count` | `int` | Headcount (allowed — only attendee *names* are rejected, not counts) | pre_process |
| `duration_days` | `int` | Event duration in days | pre_process |
| `venue_type` | `str` | Free-text venue category (e.g. "hotel", "convention_center") | pre_process |
| `format` | `str` | `"in_person"` or `"hybrid"` | pre_process |
| `event_name` | `str` | Free text, sanitized (S-2 prompt-injection + sensitive-data scan) | pre_process |
| `special_requirements` | `str` | Free text, sanitized | pre_process |
| `notes` | `str` | Free text, sanitized, optional | pre_process |
| `checklist_template` | `dict` | KB-selected phase structure (`event_type`, `fallback`, `phases`) | main (inner: checklist_template_select) |
| `checklist_markdown` | `str` | LLM-elaborated checklist (empty in `template_only`) | main (inner: checklist_generate) |
| `vendor_briefs_markdown` | `str` | LLM-drafted vendor briefs (empty in `template_only`) | main (inner: vendor_brief_draft) |
| `timeline_markdown` | `str` | LLM-generated master timeline (empty in `template_only`) | main (inner: timeline_generate) |
| `final_document_markdown` | `str` | Final document set + mandatory disclaimer | post_process |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types) — `checklist_template` is a `dict`
  of primitives/lists-of-strings only, no nested objects beyond that.
- No JWT, API keys, credentials in State (checkpoint DB leakage).
- No attendee names, company names, or budget figures in State (proposal §3) — enforced by
  `EventParamIngestNode._extra_security_gate_input()` (S-1/S-2) and
  `OutputValidateNode._extra_security_gate_output()` (S-3).
- `InvocationContext` rule *(general — not currently exercised by this template; the only
  credential this agent needs, `ANTHROPIC_API_KEY`, is resolved once at server startup, see
  Framework Utilization below)*: if any future node needs it, obtain it via
  `InvocationContext.from_state(state)` inside `execute()` only, and never store it in State.
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible).

## Framework Utilization

### Shared Components Used
- [ ] `InvocationContext.from_state(state)` — **NOT** used by any node. The single credential
      this template needs (`ANTHROPIC_API_KEY`) is resolved once at server startup
      (`src/api/server.py`, mirroring a bootstrap-time pattern used in earlier projects for
      `AnthropicClient`, which requires the key at construction time — before any per-request
      `InvocationContext` exists) and passed into the compiled agent's config.
- [ ] ConnectionPolicy (retry/timeout strategy) — not used; no external service beyond the LLM.
- [ ] SecurityViolationError — not explicitly raised; S-1/S-2 rejection sets `status=ERROR` +
      `error_log` (framework convention), S-3 rejection
      raises `RuntimeError` (matches the `OutputValidateNode` precedent used in earlier projects).
- [x] S-2: `_extra_security_gate_input()` — `EventParamIngestNode` rejects (a) any payload
      whose raw text contains a forbidden-key structural marker, a currency-figure pattern, a
      company-legal-entity-suffix pattern, or a cue-worded attendee-name pattern
      (`src/services/sensitive_event_data_scan.py::contains_sensitive_event_data`), and
      (b) any payload matching a known prompt-injection phrasing
      (`src/services/prompt_injection_scan.py::contains_prompt_injection`) — **MANDATORY per
      proposal §3**, applied before any of the 3 downstream LLM nodes can see the payload.
- [x] S-3: `_extra_security_gate_output()` — `OutputValidateNode` re-scans the finalized
      document text for the same sensitive-data signal, expressed as free-text patterns since
      the output is prose, not structured JSON (`contains_sensitive_event_data_text`) —
      defense-in-depth in case the LLM (`full_generation` mode) invents an attendee/company
      reference or budget figure despite only ever seeing sanitized, aggregate-only input.
- [x] S-4: `emit_trace_event()` — every node emits at least one domain event on its success path
      (`event_params_ingested`, `checklist_template_selected`, `checklist_generated`,
      `vendor_briefs_drafted`, `timeline_generated`, `document_set_finalized`). This is
      success-path domain-event coverage, not "every invocation path" — every node's
      `execute()` returns early on a validation/S-1/S-2 rejection, before its
      `emit_trace_event()` call is reached, so no domain event fires on a rejected request
      (see `docs/03_test_spec.md` TC-11 correction, eng-moderator MEDIUM, 2026-07-20). The
      framework's own `node_start`/`node_complete`/`node_error` lifecycle events (distinct from
      these domain events) do fire unconditionally on every path — see PB-1/PB-6.

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)
> - Custom `BaseNode` subclass → must implement `_security_gate_input()` and
>   `_security_gate_output()` directly (`@abstractmethod` — omission raises `TypeError` at instantiation)

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — `MiceEventPlanningGraphNode` wraps
  `MiceEventPlanningGraph` (inner `BaseGraph`).
- **Composition target**: `src/graph/domain_workflow_graph.py`
- **Error propagation strategy**: `propagate` (default) — an inner-graph error surfaces as
  `SubgraphError` in the outer graph; fail fast, no silent partial document set.

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: `framework/` and `shared/` only (no `agents/base/` required)

## Known Limitation — MICE Checklist KB Is Illustrative, Not Sourced Tourism Agency/JNTO Data

`src/services/data/mice_checklist_templates.json` is an illustrative dataset authored by the
implementing engineer — NOT a sourced or versioned extract of Japan Tourism Agency or JNTO MICE
guideline material, despite the source proposal listing those as the intended KB source (§10).
Every task line is explicitly prefixed to disclose this. See `src/services/data/README.md` and
README.md Known Limitations. Every deploying company must review generated checklists against
actual current guidance before relying on them for real event planning.

## Known Limitation — Sensitive-Data and Prompt-Injection Detection Are Heuristics

`sensitive_event_data_scan.py` (attendee/company name, budget detection) and
`prompt_injection_scan.py` are regex/keyword heuristics, not certified NER/PII detectors or a
semantic injection classifier — they will miss novel phrasings and can false-positive on
legitimate text. See README.md Known Limitations.

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | **AgentBaseGraph** | Fixed 6-step pipeline determined entirely by input parameters — no autonomous think→act loop needed |
| Composition pattern | Step-helper (pure-Python, 3 `FunctionNode`s) | GraphNode + inner `BaseGraph` | **GraphNode + inner graph** | Current scaffold convention (`src/examples/graph_cat2_sample.py`); matches the precedent used in earlier projects |
| Checklist structure source | LLM invents phase tasks from scratch each call | Deterministic KB lookup (`mice_checklist_kb_service.py`), LLM only elaborates | **Deterministic KB lookup** | Consistency across calls for the same event type/format is a core value proposition (proposal §9 "eliminates from-scratch recreation") — the LLM must not silently vary the base structure |
| LLM-free execution path | None (always require LLM) | Add `template_only` mode | **Added `template_only` mode** | Without it, the pipeline cannot be exercised in CI/Stage ⑤ STG without a real `ANTHROPIC_API_KEY`; also independently useful (quick KB-structure preview without LLM cost/latency) |
| Unknown `event_type` handling | Hard reject at ingest | Fall back to generic "other" KB structure, still process | **Fall back, don't reject** | Proposal §11 risk #2 explicitly calls for "a fallback structure for 'other' event types" — a typo or novel event type should not block the caller |
