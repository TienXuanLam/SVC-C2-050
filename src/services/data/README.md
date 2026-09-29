# MICE checklist KB — data source disclosure

`mice_checklist_templates.json` is an **illustrative dataset authored by the implementing
engineer**, not a sourced or versioned extract of Japan Tourism Agency or JNTO MICE guideline
material. Every task line is explicitly prefixed `[Illustrative example, not sourced Tourism
Agency/JNTO text]` for exactly this reason — see the source proposal
(source proposal §10 Technical Feasibility #2), which flags
"Japan Tourism Agency MICE guidelines" and "JNTO MICE operator standards" as inputs to build
the KB from, not as content already verified against those sources in this implementation.

**Coverage**: 5 event types (conference, agm, incentive, product_launch, exhibition) explicitly
named in the proposal, each with 6 phases (T-90/T-60/T-30/T-7/event_day/post_event), plus an
`other` fallback (proposal §11 risk #2 mitigation) for event types outside the initial five, and
a `hybrid_addon_tasks` block merged into T-30/T-7/event_day when `format == "hybrid"` (proposal
§4 note).

**Before production use**: replace with a real, sourced, versioned corpus derived from published
Japan Tourism Agency / JNTO MICE guideline material, and update `curriculum_revision`-equivalent
provenance tracking accordingly. Until then, do not present generated checklists as verified
Tourism Agency/JNTO-conformant to a customer — the illustrative-source disclaimer must remain
visible in generated output (see `docs/02_design.md` Known Limitation).

To swap in a real corpus: set `kb_path` in `config/config.yaml` to point at a replacement JSON
file matching this file's `{"event_types": {...}, "hybrid_addon_tasks": {...}}` shape.
