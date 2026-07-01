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

- [x] Exempt deterministic entity types from scrub/suspicious name-shape heuristics [ROUTINE] <!-- id:a1c2 -->
  - **Acceptance**: `scrub()` applies its heuristic removal chain (stoplists,
    structural/section-link regexes, isolated-POS gate) only to NER-derived
    types (`person`, `org`, `loc`, `misc`) and unknown types; deterministic
    types (`datetime`, `amount`, `iban`, `email_address`, `phone_number`,
    `url`, `org_hint`, `linkedin_profile`, `github_profile`, `invoice_id`,
    `tracking_id`, `registration_code`, `social_handle.*`) are never removed by
    those heuristics. `is_suspicious("datetime", …)` returns `None` (new
    dispatch entry — canonicalisation already validated the span). Existing
    scrub behaviour for NER types is unchanged (current test_scrub.py stays green).
  - **Tests**: `tests/test_scrub_type_awareness.py` — `test_scrub_keeps_datetime_relative_value`,
    `test_scrub_keeps_german_datetime_value`, `test_scrub_keeps_pattern_type_with_stoplist_value`,
    `test_scrub_still_drops_ner_person_stoplist_value`,
    `test_suspicious_datetime_numeric_not_suspicious`,
    `test_suspicious_datetime_time_not_suspicious` (currently RED)
  - **Done-check**: `uv run pytest tests/test_scrub_type_awareness.py tests/test_scrub.py tests/test_suspicious.py`
  - **Context**: `src/zkm_ner/convert.py::scrub` (`_is_heuristic_candidate`),
    `src/zkm_ner/suspicious.py` (`_PREDICATES`). See ARCHITECTURE.md §6–7.
    Scrub-only change — no extraction-output change, no `model_version` bump.

- [x] Validate amount currency codes against a known-currency allowlist [ROUTINE] <!-- id:4352 -->
  - **Acceptance**: `extract_amounts` no longer emits `amount` entities for
    3-uppercase-letter tokens that are not currencies (`DIN 1045`, `ISO 9001`,
    `MEZ 14` produce no amount); all ISO 4217 active codes plus `BTC`/`ETH`
    still extract in both prefix and suffix position; symbol forms (`€`, `SFr.`,
    `CHF`) unaffected. Bump a new `amount-v2` (replacing `amount`'s share of the
    extractor key — add `amount-v2` alongside the existing components) in
    `model_version()`.
  - **Tests**: `tests/test_amount_currency_allowlist.py` — `test_din_standard_not_amount`,
    `test_iso_standard_not_amount`, `test_timezone_abbrev_not_amount`,
    `test_real_codes_still_extracted_prefix`, `test_real_codes_still_extracted_suffix`,
    `test_crypto_tickers_allowed`, `test_model_version_bumped_for_amount_allowlist` (currently RED)
  - **Done-check**: `uv run pytest tests/test_amount_currency_allowlist.py tests/test_extract_amounts.py`
  - **Context**: `src/zkm_ner/patterns.py::extract_amounts` (filter after
    `_canonical_amount`, which does NOT validate codes — `zkm.canonical` is core
    and read-only from here, so the allowlist lives in this plugin).
    `src/zkm_ner/version.py`. ARCHITECTURE.md §2, §5.

- [x] Skip hidden directories in convert's full-store sweep [ROUTINE] <!-- id:2b76 -->
  - **Acceptance**: `convert(store, cfg)` with `created=None` ignores `.md`
    files under any dot-prefixed directory (e.g. `.zkm-state/`, `.git/`),
    using the same path predicate as `scrub()`. An explicit `created=[…]` list
    is honoured verbatim (caller's responsibility — no filtering).
  - **Tests**: `tests/test_convert_hidden_dirs.py` —
    `test_full_sweep_skips_dot_directories`,
    `test_full_sweep_still_processes_visible_files`,
    `test_created_list_not_filtered` (currently RED)
  - **Done-check**: `uv run pytest tests/test_convert_hidden_dirs.py tests/test_convert.py`
  - **Context**: `src/zkm_ner/convert.py::convert` (`md_files = …rglob…`) vs the
    dot-dir filter in `scrub()`. No extraction-output change for visible files
    → no `model_version` bump.

- [x] Single-source the plugin version (pyproject ↔ plugin.yaml ×2 ↔ PLUGIN_VERSION) [ROUTINE] <!-- id:df05 -->
  - **Acceptance**: `zkm_ner.convert.PLUGIN_VERSION` is derived at import via
    `importlib.metadata.version("zkm-ner")` (fallback: parse the packaged
    `src/zkm_ner/plugin.yaml` when metadata is unavailable); both `plugin.yaml`
    copies carry the pyproject version; a drift-guard test keeps them locked
    for future bumps. Per the polyrepo loose-0.x rule this fix is a version
    bump itself (minor) — tag `vX.Y.Z` in the same commit as the pyproject bump.
  - **Tests**: `tests/test_version_consistency.py` —
    `test_plugin_version_matches_package_metadata`,
    `test_root_plugin_yaml_matches_package_metadata`,
    `test_packaged_plugin_yaml_matches_package_metadata` (currently RED:
    pyproject=0.18.1, root plugin.yaml=0.18.0, PLUGIN_VERSION="0.18.0")
  - **Done-check**: `uv run pytest tests/test_version_consistency.py && uv run pytest`
  - **Context**: `pyproject.toml`, `plugin.yaml`, `src/zkm_ner/plugin.yaml`,
    `src/zkm_ner/convert.py`. ARCHITECTURE.md §11. After editing deps/version,
    re-run `uv sync` so the editable install's metadata refreshes before testing.

- [x] Accept lowercase/mixed-case IBANs in the IBAN extractor [ROUTINE] <!-- id:b081 -->
  - **Acceptance**: `extract_ibans` matches IBANs written in lower or mixed
    case (`de89 3704 0044 0532 0130 00`); `value` keeps the raw casing,
    `canonical` is uppercase compact, mod-97 checksum is computed on the
    uppercased compact form so `valid` is correct; uppercase behaviour and the
    no-match guards (adjacent alnum, length bounds) are unchanged. Bump
    `iban-v1` → `iban-v2` in `model_version()`.
  - **Tests**: `tests/test_iban_case.py` — `test_lowercase_iban_extracted`,
    `test_lowercase_iban_checksum_valid`, `test_mixed_case_iban_canonical_uppercase`,
    `test_model_version_bumped_for_iban_case` (currently RED)
  - **Done-check**: `uv run pytest tests/test_iban_case.py tests/test_extract_ibans.py`
  - **Context**: `src/zkm_ner/patterns.py` (`_IBAN_RE`, `_mod97`,
    `extract_ibans`), `src/zkm_ner/version.py`. `zkm.canonical.iban` already
    uppercases. ARCHITECTURE.md §2, §5.

- [x] Match invoice IDs glued to the keyword separator [ROUTINE] <!-- id:2512 -->
  - **Acceptance**: `extract_invoice_ids` matches when the separator carries no
    trailing space (`Rechnungsnummer:12345`, `Invoice #12345`) in addition to
    the current spaced forms; a keyword with NO separator at all
    (`Rechnungsnummer12345`) still does not match. Bump `invoice-v1` →
    `invoice-v2` in `model_version()`.
  - **Tests**: `tests/test_invoice_separator.py` —
    `test_invoice_hash_glued`, `test_rechnungsnummer_colon_glued`,
    `test_no_separator_still_rejected`, `test_model_version_bumped_for_invoice_separator`
    (currently RED)
  - **Done-check**: `uv run pytest tests/test_invoice_separator.py tests/test_patterns.py`
  - **Context**: `src/zkm_ner/patterns.py::_INVOICE_KEYWORD_RE` — the
    `(?:\s*[:\-=])?\s+` tail requires whitespace; rework to require at least one
    separator char (whitespace OR punctuation), not necessarily trailing space.

- [x] Keep scrub and the extraction cache coherent [HARD — meeting] — DECIDED 2026-06-23 (zkm/docs/meeting-notes/2026-06-23-1807-zkm-amendments-removal-coherence.md, D1): tombstone + emit_set. Design closed; decomposed into the [ROUTINE] children below (id:0566 + id:fa5a here; id:29ac is core zkm, routed to the shared inbox). — gate cleared 2026-06-24 (relay review): the 3 decomposed child seams ARE promoted — id:0566 + id:fa5a are open [ROUTINE] items in this ROADMAP with red specs (tests/test_tombstone_store.py, tests/test_convert_tombstone_filter.py confirmed RED), id:29ac routed to the core zkm inbox. The id:3801 dirty-guard residue re-applied a stale gate whose unblock condition was already satisfied. <!-- id:7b4e -->
  - **Decision (D1)**: cache stays **immutable / single-writer** (scrub must NOT
    rewrite cache entries — breaks idempotence-by-construction, data-loss risk).
    Instead `scrub(dry_run=False)` writes a per-store tombstone keyed
    `(scope, type, value)` per removed entity; `convert` filters the cached set
    through the tombstones and asserts the filtered set via core `emit_set`
    (mode="set"), whose `_retractable_values` clears the resurrected values from
    frontmatter. Absorbs both heuristic AND human FP removals. Rejected:
    scrub-rewrites-cache (b), port-upstream-into-pipeline (can't absorb human FP;
    verifier-cost blowup), hybrid (two coherence paths). No tombstone-GC until
    list growth is observed (observe-first).

- [x] Per-store tombstone store: `scrub(dry_run=False)` records a `(scope,type,value)` tombstone per removed entity [ROUTINE] <!-- id:0566 -->
  - **Acceptance**: a new `src/zkm_ner/tombstone.py` exposes a `TombstoneStore`
    persisted under `<store>/.zkm-state/` (per-store, single-writer), keyed on
    the `(scope, type, value)` triple; `add()` is idempotent (set semantics),
    `is_tombstoned(scope, type, value)` and `all()` read it back across fresh
    instances. `scrub(dry_run=False)` writes one tombstone per removed entity
    (heuristic removals now; verifier-drop removals too); a `dry_run=True` scrub
    writes NONE. Scope is taken from the removed entity (`body` default,
    `signature`/`salutation` preserved). Scrub-only / state-file change — no
    extraction-output change → **no `model_version` bump**. Does NOT touch
    convert's emit path (that is id:fa5a).
  - **Tests**: `tests/test_tombstone_store.py` — `test_tombstone_store_roundtrip`,
    `test_tombstone_key_is_scope_type_value_specific`, `test_tombstone_add_is_idempotent`,
    `test_tombstone_lives_under_zkm_state`, `test_scrub_writes_tombstone_per_removed_entity`,
    `test_scrub_dry_run_writes_no_tombstone`, `test_scrub_tombstone_records_entity_scope`
    (currently RED — no tombstone module yet).
  - **Done-check**: `uv run pytest tests/test_tombstone_store.py tests/test_scrub.py`
  - **Context**: `src/zkm_ner/convert.py::scrub` (the `cleaned`/`removed` loop and
    the `if not dry_run:` write block ~L503). State-dir convention mirrors
    `zkm.extraction_cache` (`<store>/.zkm-state/<thing>/`). ARCHITECTURE.md §5/§6.
    Independent of id:fa5a (can land first); id:fa5a consumes this store.

- [x] convert: filter the cached entity set through tombstones, switch `emit`→`emit_set` [ROUTINE] <!-- id:fa5a -->
  - **DEPENDS ON id:29ac** (core: add `"entities"` to `zkm.amendments._SET_FIELDS`)
    AND id:0566 (the tombstone store). Until 29ac lands, `emit_set` on entities is a
    no-op for retraction — the resurrection-prevention test cannot pass. Do NOT close
    this item until 29ac is merged in core and `uv sync` picks it up.
  - **Acceptance**: `convert._process_file` reads the cached entity set, drops any
    entity whose `(scope, type, value)` is tombstoned (id:0566), and asserts the
    filtered set via `emit_set` (mode="set") instead of legacy `emit`. The cache
    is NOT rewritten (single-writer invariant). After `scrub(dry_run=False)` removes
    an entity, a subsequent full-sweep `convert(created=None)` on the unchanged store
    (cache hit) does NOT resurrect it through union-merge. Switching emit→emit_set is
    a behaviour/semantics change to the amendment record (mode) but not to extraction
    OUTPUT values → confirm whether `model_version` needs a bump (the entity values are
    unchanged; the cache key is unchanged — **no bump expected**, but state it explicitly
    in the commit).
  - **Tests**: `tests/test_convert_tombstone_filter.py` — `test_convert_uses_emit_set_for_entities`,
    `test_convert_filters_tombstoned_entity_from_emitted_set`,
    `test_scrub_then_full_sweep_does_not_resurrect` (currently RED).
  - **Done-check**: `uv run pytest tests/test_convert_tombstone_filter.py tests/test_convert.py`
  - **Context**: `src/zkm_ner/convert.py` (`emit` import L17 → add `emit_set`; the
    `emit(...fields={"entities": entities}...)` call in `_process_file`). Core
    `zkm.amendments.emit_set` is shipped; `_SET_FIELDS` gains `entities` via id:29ac.
    ARCHITECTURE.md §5/§6.

## Gated — do NOT execute (listed for visibility only)

- **Temporal NER L2+L3 design note** (TODO id:6f3a) — gated on L1
  open-set noise being measured. Design-note work, lives in core
  `docs/entity-model.md`, not here.
- **N9e closed-loop learned denylist** (TODO id:5a0b) — gate cannot
  fire (N9d closed via Gate C; requires ≥5 verifier-override cases). No tests,
  no infrastructure.
