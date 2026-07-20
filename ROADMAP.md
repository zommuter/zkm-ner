# Roadmap <!-- fables-turn roadmap v1 -->

Executor-facing task spec. Each item is sized for ONE Sonnet session. Items are
the single source of truth — TODO.md carries only a summary line. Executors tick
checkboxes; only the reviewer adds, removes, or re-scopes items.

All red tests live in `tests/` and are mapped with `# roadmap:XXXX` comments.
Run any item's done-check from the repo root after `uv sync --extra dev`.
Remember the cache-key rule: a fix that changes extraction output must bump the
matching component of `model_version()` in `src/zkm_ner/version.py` (and the
test pinning that string) in the same commit.

## Items

- [ ] [INPUT — meeting] **§Precision doctrine in `docs/ner.md`** — add the three arms (unverifiable→precision-first / checksum-verifiable→recall+valid:false / closed-set→minimal+evidence-gated); annotate each type-table row with its class; new types declare class on add. (decided 2026-06-13-1413-ner-false-positive-doctrine.md) 🚧 blocked on placement decision: `docs/ner.md` lives in core zkm, not this repo — relocate the file/§ here OR route the edit to core (REVIEW_ME box; retagged from apex-triage [ROUTINE] by relay review 2026-07-02) <!-- id:b99e -->

- [ ] [INPUT — meeting] **zkm-ner currency (4352)** — freeze allowlist at ISO-4217 ∪ {BTC, ETH} (code half SHIPPED as ROADMAP id:4352); document the census-logged extension bar in `ner.md`. 🚧 same placement gate as id:b99e — `ner.md` is a core-zkm file (retagged from apex-triage [ROUTINE] by relay review 2026-07-02) <!-- id:f40c -->

- [ ] [INPUT — meeting] [INBOUND routed:fa25 from zkm-inventory] Amender extracts spurious scope:body entities from markdown TABLE syntax — pipe-table header/cell tokens (Value/Location/Status) misparsed as org/person; write-back then breaks CLI-level idempotence of downstream converts (surfaced via zkm-inventory drive/device md tables). Fix zkm-ner to not treat md table tokens as mentions (or exclude table cells); alt = amender-exclude inventory md. 🚧 qualified by relay review 2026-07-12: NOT promoted to ROADMAP — genuine approach fork (zkm-ner textfilter "class-8" table-cell filter vs zkm-inventory-side amender-exclude, cross-repo) PLUS a precision/recall judgment (which table tokens to drop; header-only is safe, but excluding all cells risks dropping real entities in data tables — ties into the precision doctrine id:b99e). /meeting candidate; see REVIEW_ME box. <!-- id:a4bd -->

## Gated — do NOT execute (listed for visibility only)

- **Temporal NER L2+L3 design note** (TODO id:6f3a) — gated on L1
  open-set noise being measured. Design-note work, lives in core
  `docs/entity-model.md`, not here.
- **N9e closed-loop learned denylist** (TODO id:5a0b) — gate cannot
  fire (N9d closed via Gate C; requires ≥5 verifier-override cases). No tests,
  no infrastructure.
- **§Precision doctrine + currency extension bar in `ner.md`** (TODO id:b99e +
  id:f40c, `[INPUT — meeting]`) — gated on a placement decision: the target file
  `docs/ner.md` lives in **core zkm**, not this repo, so a zkm-ner executor
  cannot edit it (relay invariant: no cross-repo edits). See the REVIEW_ME box.
  An apex DQ triage tagged them `[ROUTINE]` 2026-07-02; review retagged to
  `[HARD — meeting]` the same day (mis-tag — un-executable here as written).
