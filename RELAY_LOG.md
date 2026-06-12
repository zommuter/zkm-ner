# Relay log <!-- merge=union; append-only — never edit or reorder past entries -->

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
