# TODO — zkm-ner

This is the work ledger for zkm-ner (Option B, decided 2026-06-30 — `~/src/zkm/docs/meeting-notes/2026-06-30-1004-per-plugin-todo-topology-revisited.md`). Executor specs: `ROADMAP.md` (relay-managed). Cross-cutting items (γ schema; the NER-doctrine REVIEW_ME boxes that span zkm-social + zkm-ner) stay in central `~/src/zkm/TODO.md`. <!-- lint-ok: file-purpose preamble -->

## Current

- [ ] **Temporal NER L2+L3 design note (deferred).** L2 = actionability classifier (which datetimes are real events/deadlines vs incidental noise) — LLM-shaped, research-grade per n9d-gate-c, gated like N9d (candidate-only, evidence before infra). L3 = Phase-4 manual-merge mention→VEVENT promotion (canonical ISO match + fuzzy summary, provenance-preserving, additive link), covering the lifecycle: newsletter mentions event → user registers → formal VEVENT appears in calendar → link them. Design note in `../../docs/entity-model.md` first. **Gate for L2:** open-set noise confirmed (L1 ships and noise level measured). See `../../docs/meeting-notes/2026-06-01-1334-contacts-calendar-plugins.md`. <!-- id:6f3a -->
- [ ] **N9e (backlog — no live trigger path).** Closed-loop verifier denylist — append-only JSONL at `<store>/.zkm-state/ner-verifier-denylist.jsonl`; one record per `(value, type)`: `{value, type, verdict, source, model_version, first_seen, heuristic_would, n_observations}`. `source ∈ {verifier, heuristic, manual}`; `verdict ∈ {drop, keep}` (drops-only direction designed; keeps-becoming-sticky deferred — precedence ambiguity). **Gate: (N9d shipped) AND (≥5 verifier-override cases observed in Stage 2 pilot).** **Status 2026-05-12: gate cannot fire — N9d closed via Gate C; verifier did not ship.** Entry remains for archival reference; no implementation path until/unless a successor verifier project replaces the gate. Conflict-resolution for allow+deny overlap unresolved — design meeting required if revived. <!-- id:5a0b -->
  - [~] **N9d-9.** Per-language accuracy lens — **not pursued** (gate closure pre-empts; reopen only if N9d is revived under a different model).
  - [~] **N9d-11.** N9e sketch into `docs/ner.md` — **not pursued** (N9e gate condition is moot; see N9e backlog entry).
- [ ] **§Precision doctrine in `docs/ner.md`** — add the three arms (unverifiable→precision-first / checksum-verifiable→recall+valid:false / closed-set→minimal+evidence-gated); annotate each type-table row with its class; new types declare class on add. (decided 2026-06-13-1413-ner-false-positive-doctrine.md) <!-- id:b99e -->
- [ ] **zkm-ner currency (4352)** — freeze allowlist at ISO-4217 ∪ {BTC, ETH}; document the census-logged extension bar in `ner.md`. <!-- id:f40c -->

## Done
- [x] Relay: ROADMAP drained — id:0566 + id:fa5a both closed [ROUTINE] (scrub↔cache coherence; id:7b4e decided+decomposed 2026-06-23, core prereq id:29ac routed to inbox) on 2026-06-26 <!-- id:9c46 -->
- [x] feat(amender): accept `created=` kwarg to restrict sweep to triggered files — tests passing (test_convert.py) on 2026-06-11
