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

## Gated — do NOT execute (listed for visibility only)

- **Temporal NER L2+L3 design note** (TODO id:6f3a) — gated on L1
  open-set noise being measured. Design-note work, lives in core
  `docs/entity-model.md`, not here.
- **N9e closed-loop learned denylist** (TODO id:5a0b) — gate cannot
  fire (N9d closed via Gate C; requires ≥5 verifier-override cases). No tests,
  no infrastructure.
- **§Precision doctrine + currency extension bar in `ner.md`** (TODO id:b99e +
  id:f40c, `[HARD — meeting]`) — gated on a placement decision: the target file
  `docs/ner.md` lives in **core zkm**, not this repo, so a zkm-ner executor
  cannot edit it (relay invariant: no cross-repo edits). See the REVIEW_ME box.
  An apex DQ triage tagged them `[ROUTINE]` 2026-07-02; review retagged to
  `[HARD — meeting]` the same day (mis-tag — un-executable here as written).
