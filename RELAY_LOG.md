# Relay log <!-- merge=union; append-only — never edit or reorder past entries -->

## 2026-06-12 — executor (sonnet)

Worked id:a1c2, id:2b76, id:2512, id:b081, id:4352 — all 5 ROUTINE items ticked.
a1c2: added `datetime` to `suspicious._PREDICATES` → `_no_suspicion`; added `_DETERMINISTIC_TYPES`
frozenset to `convert.scrub._is_heuristic_candidate` so datetime, amount, iban, email_address,
phone_number, url, org_hint, linkedin_profile, github_profile, invoice_id, tracking_id,
registration_code, and social_handle.* bypass all heuristic removal (stoplist, POS gate,
structural artefact regexes). 2b76: applied the same hidden-dir filter already in scrub() to
the full-sweep branch of convert(). 2512: reworked `_INVOICE_KEYWORD_RE` separator from
`(?:\s*[:\-=])?\s+` to `(?:(?:\s*[:\-=])\s*|\s+|(?<=\#))` so glued forms like
`Rechnungsnummer:RG-…` and `Invoice #12345` match; no-separator guard (`Rechnungsnummer12345`)
stays rejected; bumped invoice-v1 → invoice-v2. b081: added inline `(?i:…)` flag to the
two-letter country-code group of `_IBAN_RE` so lowercase/mixed-case IBANs with all-digit
BBANs match; `_mod97` now called on `compact.upper()` for correct letter-to-digit conversion;
bumped iban-v1 → iban-v2. 4352: added `_ISO_4217_ACTIVE` frozenset (ISO 4217 + BTC/ETH) to
patterns.py; `extract_amounts` rejects matches where `_canonical_amount` returns a 3-letter
code not in the allowlist; also strips trailing sentence-punctuation (`,;:`) that the greedy
number pattern consumed; added amount-v2 component to `model_version()`.
Friction: b081 required two false-start approaches (IGNORECASE breaks word boundaries; body-upcase
breaks multi-IBAN sentences) before settling on the inline `(?i:[A-Z]{2})` country-only flag.
id:df05 skipped — requires a tagged version bump which executors must not create.

## 2026-06-12 22:00 — reviewer (claude-fable-5)

Handoff C1–C4 on branch relay/handoff-20260612 (base: main @ f9d00b4, v0.18.1).
C1 added the missing ARCHITECTURE.md (11 decisions with rationale) and a fresh
CLAUDE.md with the relay pointer. C2 derived 6 ROUTINE + 1 HARD roadmap items;
gated work (central id:6f3a temporal L2+L3, N9e denylist) listed do-not-execute.
C3 wrote 24 verified-red spec tests + 3 documented green guards across 6 files;
baseline 284 tests stay green (287 passed / 24 failed total). C4 added @manual
Gherkin for the convert/scrub CLI journeys and a 6-entry REVIEW_ME.md.
Surprises: four version carriers had silently drifted (pyproject 0.18.1 vs root
plugin.yaml/PLUGIN_VERSION 0.18.0); scrub's type-agnostic POS gate provably
removes valid datetime entities ("tomorrow" → NOUN); any 3-uppercase-letter
token + number is extracted as an amount ("DIN 1045", "ISO 9001"). C5 not
budgeted this turn. NOTE (core repo, not this plugin): the zkm-index
self-scope + gaming-lockfile item (central id:1098 / id:f631) was recently
executed and is awaiting USER verification — intentionally not touched or
referenced by any roadmap item here.

## 2026-06-12 21:45 — reviewer (claude-fable-5)

Handoff: first ARCHITECTURE.md (11 decisions); ROADMAP 6 ROUTINE + 1 HARD backed by 24 verified-red tests: scrub's type-agnostic POS gate deletes valid datetime entities; 3-uppercase+number amount FPs (DIN 1045/ISO 9001 confirmed); convert sweeps hidden dirs scrub skips; 4-way version drift 0.18.1/0.18.0; lowercase IBANs; invoice regex gaps. HARD: scrub/extraction-cache coherence (scrubbed entities resurrect via cached set-union). Gated id:6f3a + N9e listed; id:1098/f631 noted pending user verification, untouched. 284 baseline green.

## 2026-06-12 23:30 — executor (sonnet, relay-loop)

Closed 5 of 6 ROUTINE items: a1c2 (deterministic-type scrub exemption), 2b76 (convert hidden-dir skip), 2512 (invoice glued separator), b081 (IBAN lowercase), 4352 (amount currency allowlist); 300 tests pass, 2 remain red (df05 version-tag item, executor-blocked).

## 2026-06-13 — executor (sonnet)

Worked id:df05 — single-sourced PLUGIN_VERSION from importlib.metadata.version("zkm-ner") with
plugin.yaml fallback for dev installs. Updated root plugin.yaml and src/zkm_ner/plugin.yaml to
match pyproject.toml; bumped all four carriers from 0.18.1/0.18.0 to 0.19.0 (minor bump per
loose-0.x rule). Drift-guard tests in test_version_consistency.py all green; full suite 311/311
pass. Version tag v0.19.0 was created by the repo's autotag commit hook.
Friction: worktree's uv.sources path = "../.." resolves incorrectly (no zkm there); worked around
by symlinking .venv from main checkout and running uv sync with absolute path during development,
reverting to relative path for the commit.

## 2026-06-13 10:03 — executor (sonnet, relay-loop)

feat(version): single-source PLUGIN_VERSION from importlib.metadata (id:df05) — bump 0.18.x→0.19.0, 311/311 tests green

## 2026-06-13 15:04 — reviewer (claude-opus-4-8, fable-standin, relay-loop)

review 20260613-1450: 1 commit audited (5510723 docs-only REVIEW_ME annotations) clean; 311 tests green; fixed contract pointer v1→v2 and TODO count 7→1

## 2026-06-13 23:43 — reviewer (claude-opus-4-8, fable-standin, relay-loop)

zkm-ner review: 1 REVIEW_ME-only commit audited clean, 311 tests green, no gaming, 4 resolved boxes pruned, 0 open [ROUTINE]

## 2026-06-16 20:03 — reviewer (claude-opus-4-8, fable-standin, relay-loop)

zkm-ner handoff: C1 refreshed stale contract pointer v2→v4 (/fables-executor→/relay executor); 311 tests green; HARD id:7b4e left specced (meeting-gated); 0 open ROUTINE

## 2026-06-22 16:01 — reviewer (claude-opus-4-8, fable-standin, relay-loop)

zkm-ner review 20260622-1601: 1 human commit audited (800f66e, ROADMAP-only) — id:78ff lane-tag migration retagged id:7b4e `[HARD — strong model]`→`[HARD — meeting]` (valid 415b grammar lane, justified by its "cross-component design with real ambiguity" rationale). gaming-scan clean; no code/test diff (tree byte-identical to prior HEAD); baseline 311/311 green (run in canonical checkout — worktree `uv run` blocked by the known `../..` uv.sources path artifact, RELAY_LOG 2026-06-13 friction). Contract pointer current at v4. Cross-ledger consistent: id:7b4e open in ROADMAP, tracked open by TODO id:9c46. No reverse-handoff needed (re-tag of an already-qualified HARD item). 0 open ROUTINE; REVIEW_ME 0 open.

## 2026-06-22 16:23 — reviewer (claude-opus-4-8, fable-standin, relay-loop)

zkm-ner review: id:78ff lane-tag migration audited CLEAN (ROADMAP-only), 311/311 green, contract v4, 0 open ROUTINE

## 2026-06-23 17:24 — reviewer (claude-opus-4-8, relay-loop)

zkm-ner review 20260623-172446: 1 commit audited (db38ff0, ROADMAP-only) — /meeting wrote D1 decision onto id:7b4e (tombstone + emit_set; meeting 2026-06-23-1807). Emitted D1's decomposition per the meeting's explicit forward-action: id:7b4e marked decided+closed [x] (design done); added two [ROUTINE] children with red specs — id:0566 (per-store (scope,type,value) TombstoneStore under .zkm-state/; scrub writes on real runs) and id:fa5a (convert filters cached set through tombstones + emit→emit_set; DEPENDS on core id:29ac). Reverse-handoff (§5b): both children reuse the meeting-minted ids (single-id-two-views, no duplicate tokens). Core prereq id:29ac is zkm-core work → routed to the shared inbox (not this plugin's TODO). Red specs: tests/test_tombstone_store.py (7) + tests/test_convert_tombstone_filter.py (3), all 10 confirmed RED (missing zkm_ner.tombstone module + emit_set not wired). Baseline 311/311 green; gaming-scan clean (no test deletions/skips/assert-removals — doc+spec-only window). roadmap-lint clean. Contract pointer current at v4. TODO id:9c46 count updated 1→2. 2 open ROUTINE; REVIEW_ME 0 open.

## 2026-06-23 19:44 — reviewer (claude-opus-4-8, fable-standin, relay-loop)

zkm-ner review: emit id:7b4e D1 decomposition — closed HARD parent, added [ROUTINE] children 0566 (tombstone store) + fa5a (convert filter+emit_set) with 10 red specs; core 29ac routed to inbox; 311/311 baseline green, gaming-scan+lint clean

## 2026-06-24 20:58 — reviewer (claude-opus-4-8, fable-standin, relay-loop)

review zkm-ner: cleared stale id:7b4e route:human gate (children id:0566+id:fa5a already promoted as open [ROUTINE]); gaming/lint/doctor clean
## 2026-06-24 — executor (sonnet)

Worked id:0566 and id:fa5a — both ROUTINE items closed.
id:0566: created `src/zkm_ner/tombstone.py` with `TombstoneStore` persisted as JSONL under `<store>/.zkm-state/tombstones.jsonl`. Set semantics (idempotent add); key is `(scope, type, value)`. Modified `scrub()` to collect removed entities in `removed_entities` list and write tombstones via a lazy `_get_tombstone_store()` on `not dry_run` — both heuristic and verifier-drop removals recorded; dry-run writes nothing. 7/7 test_tombstone_store.py tests green.
id:fa5a: added `emit_set` to imports; modified `_process_file` to load `TombstoneStore` and filter entities by tombstone before emitting; switched from `emit` to `emit_set` (mode="set") so core's `_retractable_values` diffs and drops stale values. Cache not rewritten (single-writer invariant). No model_version bump (entity values unchanged). 3/3 test_convert_tombstone_filter.py tests green.
Full suite: 321/321 pass (up from 318 with 3 red). Both items ticked in ROADMAP.md.
Friction: worktree uv.sources path="../.." artifact (known since 2026-06-13) blocked `uv run` from worktree; worked around by symlinking main checkout's .venv into worktree and using PYTHONPATH to prioritize worktree's src/ over editable install.

## 2026-06-24 21:08 — executor (sonnet, relay-loop)

executor 2026-06-24: closed id:0566 (TombstoneStore) + id:fa5a (convert tombstone filter + emit_set); 321/321 tests green

## 2026-06-26 09:43 — reviewer (claude-opus-4-8, fable-standin, relay-loop)

review: audit window clean (1 conformance commit); reconciled TODO id:9c46 (ROADMAP drained, id:0566+id:fa5a closed); 321/321 green

## 2026-06-30 12:19 — reviewer (claude-opus-4-8, fable-standin, relay-loop)

review: Option-B TODO migration verified legit, ROADMAP drained + 321 tests green; b99e/f40c left as /meeting candidates (target core docs/ner.md) [id:b99e,f40c]
