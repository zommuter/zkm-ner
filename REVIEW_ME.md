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
  **Update 2026-07-02 (review):** an apex DQ triage (commit e7eb3ce) lane-tagged
  both items `[ROUTINE]` without resolving this placement question — that tag
  would have made unpromoted-scan demand a handoff promoting un-executable
  cross-repo specs into this ROADMAP. Review retagged both to `[HARD — meeting]`
  (verified `docs/ner.md` exists only in core zkm; this repo has no `docs/`).
  The /meeting placement decision above is still the unblock; if it chooses
  "route to core", close both here with a pointer and inbox-route the doc edits.

- [ ] **a4bd (routed:fa25 from zkm-inventory) — md-table entity extraction: /meeting
  candidate, NOT a promotable [ROUTINE].** zkm-inventory's drive/device markdown tables
  make the amender emit spurious `scope:body` org/person entities from pipe-table header
  and data cells (Value/Location/Status), and the write-back then breaks CLI-level
  idempotence of downstream converts. Two genuinely divergent fixes: **(A)** zkm-ner side
  — extend `textfilter.py` with a new "class-8" table-cell filter (natural home: the file
  already has class-1/5/7 pipe/separator/empty-cell filters, so an executor would slot it
  there); **(B)** zkm-inventory side — `amender-exclude` the inventory md so it never runs
  NER over structural tables. (A) also carries a precision/recall sub-judgment: dropping
  *header* tokens is safe, but blanket-excluding *all* table cells would silently drop
  legitimate entities that live inside data tables (a contacts/asset table listing real
  people/orgs) — exactly the class of call the NER **precision doctrine** (id:b99e, still
  meeting-gated on placement) governs. Because (A)-vs-(B) is cross-repo and the "which
  tokens" line is a doctrine call, the reviewer left it in TODO as `[INPUT — meeting]`
  rather than writing a red spec that would prematurely commit to approach (A). Meeting
  should pick A/B and, if A, the drop granularity (header-only vs cell-content heuristic).
  (Qualified — reverse-handoff — by relay review 2026-07-12.)
