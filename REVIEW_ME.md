# Human review queue <!-- budget: 15 min -->

Judgment calls encoded in red tests — confirm or correct the interpretation.
Max ~10 open boxes; the reviewer prunes resolved ones each review turn.

R1 judgment calls confirmed by user 2026-06-13 (batch triage, commit 6e4706d);
their roadmap items (a1c2, 2b76, 2512, df05) are closed and verified green.

- [ ] **b99e + f40c target core `docs/ner.md`, not a file in this repo.** The
  Option-B migration (zkm meeting 2026-06-30-1004) moved these two doc-doctrine
  items into zkm-ner's TODO because NER doctrine is conceptually zkm-ner's — but
  the file they edit, `docs/ner.md`, lives in the **core zkm repo**, not the
  zkm-ner plugin repo. As written they are NOT one-Sonnet-session zkm-ner
  executor specs (an executor in this worktree cannot edit a sibling repo). They
  are deliberately left in TODO (not promoted to ROADMAP) pending a placement
  decision — **/meeting candidate**: relocate `docs/ner.md` (or its NER-precision
  §) into zkm-ner, OR route these two doc edits to the core zkm ledger. f40c's
  code half (freeze allowlist at ISO-4217 ∪ {BTC,ETH}) already shipped as the
  closed ROADMAP item id:4352 — only the `ner.md` documentation remains.
  (Review 2026-06-30; relay-doctor flagged "ROADMAP drained, 3 unpromoted TODO" —
  5a0b/6f3a are already in ROADMAP's Gated section, this box covers b99e+f40c.)
