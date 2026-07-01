# zkm-ner — NER amender plugin for zkm

Extracts entity mentions (persons, orgs, locations, contact details, value types)
from knowledge-store markdown bodies and merges them into `entities:` frontmatter
via `zkm.amendments`. **Amender pattern**: `convert()` always returns `[]` and
never writes a document body.

See `ARCHITECTURE.md` for design decisions with rationale and rejected alternatives.
See `ROADMAP.md` for the executor-facing task queue. The central work ledger is
`~/src/zkm/TODO.md` (N-prefix items); this repo's `TODO.md` is a stub pointing there.

## Commands

```bash
uv sync --extra dev          # env; installs spaCy de/en small models as pinned wheels
uv run pytest                # full suite — hermetic: no network, no live LLM, tmp stores
uv run pytest -k <expr>      # one test / one roadmap item's done-check
uv run ruff check <files>    # lint (line-length 100, py311); keep files YOU touch clean
```

This repo must live at `plugins/zkm-ner/` inside a zkm core checkout — the
editable dep is `zkm = { path = "../..", editable = true }` in `[tool.uv.sources]`.
A standalone clone will not `uv sync`.

## Layout

```
convert.py              # filesystem-discovery shim: re-exports zkm_ner.convert.{convert,scrub}
plugin.yaml             # filesystem-discovery manifest (root copy)
src/zkm_ner/
├── convert.py          # convert() amender entry + scrub() retroactive cleanup
├── extract.py          # pipeline orchestrator: patterns → NER → POS gate → post-filters
├── patterns.py         # deterministic regex overlay (email, phone, URL, IBAN, amount, …)
├── spacy_backend.py    # de/en small models, langdetect routing, datetime spans
├── gliner_backend.py   # opt-in GLiNER backend (extra: zkm-ner[gliner])
├── textfilter.py       # pre-strip + post-extraction FP filters (stoplists, artefact regexes)
├── suspicious.py       # per-type "suspicious" predicates (verifier dispatch + pilot tooling)
├── verifier.py         # two-tier LLM verifier (dormant — N9d closed via Gate C)
├── datetime_canon.py   # dateparser wrapper → ISO 8601, doc-date anchored
├── version.py          # model_version() — extraction-cache key component
├── _types.py           # Entity dataclass (γ typed slots)
├── plugin.yaml         # wheel-packaged manifest copy
└── gazetteers/orgs.yaml
scripts/                # pilot / migration tooling (not part of the wheel contract)
tests/                  # pytest; conftest provides make_store / make_md helpers
```

## Gotchas (hard-won; do not rediscover)

- **Two `plugin.yaml` copies** (repo root for filesystem discovery, `src/zkm_ner/`
  for the wheel) and the `PLUGIN_VERSION` constant in `src/zkm_ner/convert.py`
  must stay in sync with `pyproject.toml` `version`. They have drifted before
  (see ROADMAP id:df05).
- **`model_version()` is a cache key.** Any change that alters extraction output
  distribution (new filter, regex fix, stoplist entry) MUST bump the matching
  `…-vN` component in `src/zkm_ner/version.py`, or stale cached results survive.
  Tests pin the current string (e.g. `textfilter-v8`) — update them in the same commit.
- **Extraction-cache key hashes `body + "\x00" + signature_block + "\x00" +
  salutation_block`** — frontmatter-only amendments (tags, etc.) must NOT bust
  the cache; adding/changing a signature or salutation block must.
- **Set-union amendment merge cannot remove entities.** `zkm scrub ner` is the
  only removal path. Known gap: scrub does not rewrite the extraction cache, so
  a later full-sweep convert can resurrect scrub-removed entities (ROADMAP id:7b4e).
- **Root-shim import in tests**: `tests/conftest.py` prepends the repo root to
  `sys.path`; older tests do `from convert import convert` (the shim), newer ones
  import `zkm_ner.*`. Both resolve to the same module objects only for
  `zkm_ner.*`; patch targets are `zkm_ner.extract.extract` and
  `zkm_ner.version.model_version` regardless.
- **Tests are hermetic**: tmp git stores via `conftest.make_store`, no network,
  no `~/knowledge`, verifier tests mock `httpx.post`. spaCy model loads are real
  (wheel-pinned) — keep new tests fast by reusing module-level model caches.
- **Heavy imports are deferred** inside functions (`spacy`, `httpx`, `frontmatter`,
  `dateparser`) — keep it that way; plugin import must stay cheap for `zkm --help`.
- **Locale**: corpora are DE/EN, store context is de_CH (CHF amounts, `20.-`
  notation, day-first dates). Phone default region is CH.

## Settled decisions — do NOT re-open

- Amenders run **default-on** after every producer convert; `--no-amenders` opts out.
- `entity.value` strings are **mentions, never UIDs** — no auto-merge, no `same_as:`.
- `user_names` config was **dropped in v0.15.0** (dedup-cardinality reframe).
- spaCy small models stay the default backend; GLiNER is opt-in only
  (384-token truncation makes it wrong for mixed-length mail corpora).

## Versioning

Follows the zkm polyrepo rule: every `pyproject.toml` version change is tagged
`vX.Y.Z` in the same commit (loose-0.x: patch = bugfix only, minor = anything else).
Bump `plugin.yaml` (both copies) and `PLUGIN_VERSION` together with pyproject.

## Relay contract <!-- relay-executor contract v6 -->

This repo is managed by a reviewer/executor relay. Load `/relay executor` before
working on any item, then follow its rules exactly.
