# zkm-ner architecture

Decisions with rationale and rejected alternatives. Companion docs in the zkm core
repo: `docs/ner.md` (pipeline + cache contract), `docs/plugin-spec.md` (amendment
merge rules), `docs/entity-model.md` (γ schema, Phase 3+).

## 1. Amender, not producer

`convert()` returns `[]` and only emits amendment records (`zkm.amendments.emit`
→ `apply_queue`). The markdown **body is single-producer** (owned by the source
plugin, e.g. zkm-eml); **frontmatter is multi-producer** via the amendment queue
with set-union merge on dedup key `(scope, type, value)`.

- Rationale: NER must enrich documents it does not own without fighting the
  producer over body content; the merge engine is the only frontmatter writer,
  so concurrent amenders cannot corrupt each other.
- Rejected: writing frontmatter directly from the plugin (race-prone, duplicates
  merge logic); a separate entities sidecar file (frontmatter is the indexed
  source of truth — DB-derived metadata must be written back to the md).
- Consequence: **set-union cannot remove**. Retroactive removal is `scrub()`'s
  job (§6). Replace-mode merge was discussed and deferred (central TODO:
  "Meeting: amendment replace-mode") — do not implement it ad hoc.

## 2. Extraction pipeline order

Per document: `strip_markdown_artefacts` (pre-strip) → pattern overlay →
NER backend → in-pipeline POS gate → post-extraction filters → overlap merge
(patterns win) → dedup on `(type, value)`.

- **Patterns first, patterns win on span overlap.** Deterministic regex +
  library validation (libphonenumber, mod-97, ISO 4217 canonicaliser) is
  higher precision than statistical NER; when spaCy labels "CHF 1'000.-" as
  MISC, the typed `amount` entity must win. The overlap filter also prevents
  value-type strings from polluting org/misc (confirmed by the E13 audit).
- **POS gate** (`extract._pos_filter`): spaCy entities pass only when
  `ent.root.pos_ == "PROPN"`; pattern entities carry `root_pos=""` and bypass.
  Rationale: class-4 pollution (common nouns as PROPN) was the largest FP class
  in the N9 pilot; root-POS is cheap because the doc is already parsed.
- Rejected: running NER first and patterns as fallback (loses precision);
  LLM-based extraction (cost/latency over a 55k-doc store; LLM enters only at
  verification, §7).

## 3. Backend: spaCy small models, doc-level language routing

`de_core_news_sm` + `en_core_web_sm`, selected per document by `langdetect`
over the first 2 kB; `lang` config forces a code; unknown codes fall back to de.
Models are pinned as wheel URLs in `[tool.uv.sources]` so `uv sync` is
deterministic and hermetic.

- Rejected as default: **GLiNER** (`gliner-multilingual-v2.1`, opt-in via
  `model: gliner` + the `[gliner]` extra) — truncates input at 384 tokens
  (~2800 chars), silently dropping document tails; acceptable only for
  short-document corpora and benchmarking.
- Rejected: large/transformer spaCy models (latency over full-store sweeps);
  sentence-level language detection (mixed-language docs accepted as a known
  limitation — doc-level detection is good enough for mail corpora).

## 4. Multi-stage false-positive filtering (pollution taxonomy)

Each filter layer maps to a pollution class identified in the N9 pilots:

| Class | Example | Layer | Where |
|---|---|---|---|
| 1 markdown fragments | `---`, table rows | pre-strip body | `strip_markdown_artefacts` |
| 2+3 header words / subject prefixes | `Subject`, `Re`, `Aw` | closed-set stoplist | `_STOPLIST` |
| 4 common nouns as PROPN | `Zeit`, `Internet` | POS gate + closed set | `_pos_filter` + `_COMMONNOUN_STOPLIST` |
| 5 pipe-cell artefacts | `\| \|` | value regex | `drop_structural_artefacts` |
| 6 salutations / sign-offs | `Best Regards` | closed-set blocklist | `_SALUTATION_BLOCKLIST` |
| 7 broken link targets | `Section 3]…` | anchored regex | `drop_section_link_artefacts` |
| HTML-entity runs | `&gt;&nbsp;` | charset regex ≤30 chars | `drop_html_entity_artefacts` |

- Doctrine: **stoplists only for closed-set garbage** (header vocab is finite);
  open-set FP classes get structural fixes (POS gate, regexes), never
  ever-growing lists. Class-4 was deliberately solved with POS + a tiny
  abbreviation set rather than a word stoplist.
- Every layer is versioned into `model_version()` (e.g. `textfilter-v8`,
  `posfilter-v1`) so a filter change auto-invalidates the cache (§5).
- Rejected: `user_names` runtime greeting stoplist — shipped v0.14.0, **dropped
  v0.15.0**: per-user config multiplied cache-key cardinality and published-repo
  genericity for marginal gain; salutation handling moved to the static
  blocklist + zkm-eml salutation-scope extraction.

## 5. Extraction cache

`zkm.extraction_cache.ExtractionCache(store, extractor_name="ner")`, key =
`(combined_sha256, model_name, model_version)` where
`combined = body + "\x00" + signature_block + "\x00" + salutation_block`.

- Body-derived key means frontmatter amendments (tags from notmuch, entities
  from this plugin) never bust the cache — re-runs on an unchanged store are
  I/O-only. The `\x00`-joined sig/sal blocks are included because scope-tagged
  entities (§8) are derived from them; a re-render that changes the signature
  must re-extract.
- `model_version` concatenates spaCy model versions + per-layer filter versions.
  Forgetting to bump it is the classic failure mode here (see CLAUDE.md gotchas).
- Known coherence gap: `scrub()` edits frontmatter but not the cache, so a
  full-sweep convert can resurrect scrub-removed entities whose removal logic
  lives only in scrub (isolated-POS, verifier verdicts). ROADMAP id:7b4e.

## 6. Scrub — the only removal path

`scrub(store, config, dry_run=True, …)` retroactively removes FPs from existing
`entities:` frontmatter: closed-set stoplists, structural/section-link regexes,
and an **isolated bilingual POS check** (DE first, EN retry; single-word values
only; keep POS ∈ {PROPN, X}). Dry-run by default; idempotent; atomic writes;
never touches `.amendments.json` attribution sidecars; supports
`resume_after_file` / `on_file_done` for interrupted long runs and a JSONL
pilot-dump for human classification gates.

- The isolated-POS check intentionally differs from the in-pipeline root-POS
  gate: at scrub time the original sentence context is gone, so the word is
  parsed in isolation; the EN retry catches English common words the DE model
  tags PROPN (`Learn`, `Link`).
- Known defect (ROADMAP id:a1c2): the heuristic candidate check is
  type-agnostic, so deterministic types (datetime, amount, …) can be removed by
  name-shape heuristics that were designed for spaCy person/org/loc/misc.

## 7. Suspicious dispatch + two-tier LLM verifier (dormant)

`suspicious.is_suspicious(type, value)` routes to per-type predicates:
name-shape heuristics for NER types, `None` (never suspicious) for
structurally-validated pattern types; unknown types fall back to the name
predicate (conservative). The verifier (`verifier.verify`) is suspicious-only:
Tier 1 value-only prompt; Tier 2 context-augmented only on "unclear"; verdicts
cached in `ExtractionCache(extractor_name="ner_verifier")` keyed on
`sha256(value:type)` with the prompt hash baked into `model_version` so any
prompt edit auto-invalidates. All errors → "unclear" → keep (fail-open on
retention, never on removal). A `with_verifier_control_pct` blind-spot tripwire
samples non-suspicious entities.

- Status: **N9d closed via Gate C** — the verifier shipped as code but is not in
  any default path; N9e (closed-loop learned denylist) is gated on ≥5
  verifier-override cases that cannot occur while the verifier is dormant.
  Do not build N9e infrastructure.

## 8. γ typed-slot schema and the Entity dataclass

`Entity(type, value, scope, canonical, standard, unit, valid, start, end,
root_pos)`; `as_dict()` emits only γ slots, omitting `canonical/standard/unit`
when unset and `valid` when True. Invariant: `canonical` must differ from
`value` (constructor raises) — "value is canonical" is expressed by
`canonical=None`, keeping frontmatter minimal. `start/end/root_pos` are
in-process only (overlap merge, POS gate) and never serialised.
Scopes: `body` (default) | `signature` | `salutation`, the latter two extracted
from zkm-eml's `signature_block` / `salutation_block` frontmatter fields with
scope overridden post-extraction.

## 9. datetime L1

spaCy DATE/TIME spans → `datetime_canon.canonicalise` (dateparser; stdlib
ISO/EU-date fallback) → γ `type: datetime` with ISO 8601 `canonical`. Relative
expressions anchor on the document's own `date` frontmatter
(`RELATIVE_BASE`), with `PREFER_DATES_FROM: future`; unparseable spans are
dropped rather than emitted raw; midnight-exact results collapse to date-only.
Unsupported langdetect codes fall back to `["de", "en"]`.

- L2 (actionability classification) and L3 (mention→VEVENT promotion) are
  **gated design work** (central id:6f3a) — not implementable here until L1
  noise is measured.

## 10. Mentions, not UIDs

`entity.value` is the mention string as written. No `id:`, no `same_as:`, no
fuzzy clustering. A name is not a unique identifier; false merges are far more
expensive to undo than manual merges are to perform. Identity resolution is a
Phase-4 manual-merge concern. (Settled — do not re-open.)

## 11. Packaging duality

The plugin is discoverable two ways: entry point `zkm.plugins:ner → zkm_ner`
(wheel install) and the repo-root `convert.py` shim + `plugin.yaml`
(filesystem/dev install, where core injects `src/` onto `sys.path`). Hence the
duplicated `plugin.yaml` (root + `src/zkm_ner/`) — both must carry the pyproject
version (drift guard: ROADMAP id:df05).
