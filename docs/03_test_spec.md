# Test Specification

## Test Strategy
- Coverage target: all business logic paths (success + validation-rejection + fail-closed) per node/service
- Test types: Unit (nodes, services), Integration (outer graph, inner graph, HTTP entry point), Proof-of-Boundary (framework contract)

## Scope Disclaimer

`src/services/data/mice_checklist_templates.json` is an illustrative dataset, not sourced
Japan Tourism Agency / JNTO guideline material (see README.md Known Limitations,
docs/02_design.md). `sensitive_event_data_scan.py` / `prompt_injection_scan.py` are
regex/keyword heuristics, not certified detectors. Tests verify the *mechanism* (KB lookup,
scan pattern matching, mode routing) is correct given whatever data/patterns are configured —
they do not and cannot verify real-world MICE guideline accuracy or exhaustive attack coverage.

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | ✅ `src/schemas/state.py` — all fields `str`/`int`/`dict` |
| TC-02 | SecurityViolationError fires on invalid input | S-1/S-2 rejection sets `status=error` (framework convention); S-3 raises `RuntimeError` | ✅ `test_event_param_ingest_node.py::test_s1_s2_rejects_attendee_name_via_call`, `test_s2_rejects_prompt_injection_via_call`; `test_output_validate_node.py::test_s3_rejects_unsafe_output` |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | ✅ no credential fields declared |
| TC-04 | InvocationContext via configurable only | Not exercised by any node (docs/02_design.md Framework Utilization) | N/A — no node calls `InvocationContext.from_state()` |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start`/`node_complete`/`node_error` absent from `execute()` body | ✅ manual review — only `emit_trace_event()` domain events |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | ✅ 0 overrides — all nodes extend via `_extra_security_gate_input()` only |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | ✅ 0 overrides |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused | ✅ `test_output_validate_node.py::test_trust_gate_rejects_anonymous_caller`, `test_graph.py::test_graph_node_trust_gate_lifecycle` |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial | Sensitive-data + prompt-injection scan on the raw payload (MANDATORY per proposal §3) | ✅ `EventParamIngestNode._extra_security_gate_input` |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial | Sensitive-data text scan on the finalized document | ✅ `OutputValidateNode._extra_security_gate_output` |
| TC-11 | S-4: ≥1 domain `emit_trace_event()` per `execute()` | Domain event emitted on the success path of every node | ✅ every node calls `emit_trace_event()` on success — correction (MEDIUM): the "every invocation path" wording in a prior revision of this row was overstated; every `execute()` in `src/nodes/` returns early on a validation/S-1/S-2 rejection *before* reaching its `emit_trace_event()` call, so no domain event is emitted on the error path — only on success. The framework's own `node_start`/`node_complete`/`node_error` lifecycle events (S-4, distinct from these domain events — see TC-05) fire unconditionally regardless of node outcome; PB-1/PB-6 below verify those, not domain-event coverage on rejection paths. |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | Framework `node_start`/`node_complete`/`node_error` lifecycle events fire on every invocation path | No silent failures | ✅ — this is the framework's own lifecycle event emission, not the domain `emit_trace_event()` calls in `src/nodes/`, which only fire on each node's success path (see TC-11 correction above) |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | ✅ `test_state_safety.py` |
| PB-3 | Level 2 → External service | Real external service connection | N/A — this template has no external service beyond the LLM (bundled JSON KB, no DB) | N/A |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | ✅ `test_import_isolation.py` |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | ✅ `test_state_safety.py` |
| PB-6 | Invoke execution order | S-1 → S-4 `node_start` → S-2 → `execute()` → S-3 → S-4 `node_complete` | Order verified | ✅ `test_pb_invoke_order.py` (discovers all 6 `src/nodes/` classes dynamically) |
| PB-7 | HITL interrupt propagation *(conditional)* | `hitl.enabled` absent from `config/config.yaml` | **Auto-waived — non-HITL** | ✅ 2 SKIPPED |

> **Pre-CoE gate checklist:** PB-1 through PB-6 are mandatory (PB-3 N/A per this template's
> architecture — no external service beyond the LLM). PB-7 auto-waived — non-HITL.

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01..07 | `prompt_injection_scan` | Clean text / "ignore previous instructions" / "disregard above" / "you are now" / "new instructions:" / `<system>` tag / empty | Correctly flags only known injection phrasings; legitimate "system" mentions (e.g. sound system) not over-flagged | ✅ `test_prompt_injection_scan.py` |
| BL-08..16 | `sensitive_event_data_scan` (structured JSON) | Clean params / forbidden keys (attendee_name, budget, nested) / budget figure in free text / company suffix in free text / attendee cue-word / malformed JSON / empty | Correctly flags only attendee/company/budget data | ✅ `test_sensitive_event_data_scan.py::TestContainsSensitiveEventData` |
| — | `sensitive_event_data_scan` (free-text output scan) | Clean markdown / budget figure / company suffix | Correctly flags only sensitive data in LLM-generated prose | ✅ `TestContainsSensitiveEventDataText` |
| BL-17..21 | `MiceChecklistKBService` | Known event type / all 5 named types / unknown type / phase completeness / hybrid format | Correct template selection, fallback behavior, and hybrid add-on merging | ✅ `test_mice_checklist_kb_service.py` |
| BL-22..38 | `EventParamIngestNode` | Valid/malformed/missing-field/invalid-format/out-of-range/boolean-coercion/oversized/invalid-mode payloads | Correct accept/reject per case; S-1/S-2 hook rejects sensitive data and prompt injection | ✅ `test_event_param_ingest_node.py` |
| — (added, eng-moderator, MEDIUM, 2026-07-20) | `EventParamIngestNode` fractional numeric input (`test_fractional_attendee_count_rejected`, `test_fractional_duration_days_rejected`, `test_whole_number_float_attendee_count_accepted`, `test_attendee_count_string_rejected`) | Fractional `attendee_count`/`duration_days` (e.g. `150.5`) / whole-number float (e.g. `150.0`) / numeric string (e.g. `"150"`) | Fractional values rejected with a specific message — `int(150.5) == 150` previously truncated silently instead of rejecting; whole-number floats still accepted; numeric strings rejected (JSON payload contract is numbers, not numeric strings) | ✅ `test_event_param_ingest_node.py` (4 new cases) |
| BL-39..41 | `ChecklistTemplateSelectNode` | Forwarded JSON rehydration, unknown event type, default KB service | Correct rehydration and KB fallback; no crash | ✅ `test_checklist_template_select_node.py` |
| BL-42..53 | `ChecklistGenerateNode` / `VendorBriefDraftNode` / `TimelineGenerateNode` | LLM success / not configured / provider exception / empty content | Fail-closed on every non-success path (all 3 nodes) | ✅ `test_checklist_generate_node.py`, `test_vendor_brief_draft_node.py`, `test_timeline_generate_node.py` |
| BL-54..60 | `OutputValidateNode` | full_generation / template_only / fallback disclosure / unsafe output / trust gate | Correct rendering per mode; S-3 blocks unsafe output; trust gate enforced | ✅ `test_output_validate_node.py` |
| BL-61..68 | Outer + inner graph integration | full_generation / template_only / invalid input / unsafe LLM / config surface / GraphNode trust gate | End-to-end correctness; regression coverage for inner-graph routing (regression-tests a real langgraph==1.1.10 bound-method bug found in an earlier project) | ✅ `test_graph.py` |
| — (added, eng-moderator, MEDIUM, 2026-07-20) | Outer graph end-to-end: fractional attendee_count invariant (`test_fractional_attendee_count_rejected_end_to_end`) | `attendee_count: 150.5`, via the fully compiled outer graph | `status=error` (never silently truncated to 150 and processed) — proves the fix survives `EventParamIngestNode`'s validation boundary end-to-end, not just the isolated node unit tests | ✅ `test_graph.py::test_fractional_attendee_count_rejected_end_to_end` |
| — | HTTP entry point | No token / wrong token / correct token | 401/401/200 with correct `node_history` | ✅ `test_server_endpoint.py` |

## Test Execution Summary
- Execution date: 2026-07-20
- Total tests: 86 (84 passed, 2 skipped — PB-7 auto-waived, non-HITL) — up from
  81/79 after adding 5 new tests (MEDIUM fix, 2026-07-20): 4 unit
  (`test_fractional_attendee_count_rejected`, `test_fractional_duration_days_rejected`,
  `test_whole_number_float_attendee_count_accepted`, `test_attendee_count_string_rejected` in
  `test_event_param_ingest_node.py`), 1 outer-graph end-to-end
  (`test_fractional_attendee_count_rejected_end_to_end` in `test_graph.py`)
- Pass: 84 / Fail: 0 / Skip: 2
- Coverage: all node `execute()` success + primary rejection paths, including fractional-value
  rejection for `attendee_count`/`duration_days` (closes a silent-truncation defect); both scan
  services' structured-JSON and free-text entry points; S-1/S-2/S-3/S-4 lifecycle for every node
  type (`FunctionNode` and `GraphNode`); end-to-end regression coverage for the fractional-value
  invariant through the fully compiled outer graph, not just the isolated node unit test
