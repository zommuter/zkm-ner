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
