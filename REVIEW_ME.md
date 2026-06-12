# Human review queue <!-- budget: 15 min -->

Judgment calls encoded in red tests — confirm or correct the interpretation.
Max ~10 open boxes; the reviewer prunes resolved ones each review turn.

- [ ] test_scrub_type_awareness.py::test_scrub_keeps_pattern_type_with_stoplist_value
  (roadmap:a1c2) — scrub's stoplists/POS gate are restricted to NER types
  (person/org/loc/misc) and unknown types; deterministic types are FULLY
  exempt, even for odd values like invoice_id "RE". Alternative: keep
  stoplists type-agnostic and only exempt the POS gate.

- [ ] test_amount_currency_allowlist.py::test_crypto_tickers_allowed
  (roadmap:4352) — currency allowlist = full ISO 4217 active-code set ∪
  {BTC, ETH} only. Wider crypto-ticker lists rejected for FP risk (any
  3-letter token would creep back in). Confirm BTC/ETH belong at all.

- [ ] test_convert_hidden_dirs.py::test_created_list_not_filtered
  (roadmap:2b76) — an explicit created= list is honoured verbatim, even for
  paths under dot-directories (caller's responsibility). Alternative:
  defensively filter created= with the same predicate.

- [ ] test_iban_case.py::test_lowercase_iban_extracted (roadmap:b081) —
  accepting lowercase IBANs widens the false-positive surface (lowercase
  shape-matches are emitted with valid:false when the checksum fails).
  Interpretation: the mod-97 gate on `valid` is sufficient; no extra
  lowercase-only confidence penalty.

- [ ] test_invoice_separator.py::test_no_separator_still_rejected
  (roadmap:2512) — at least one explicit separator character (whitespace or
  :-=# punctuation) is required between keyword and ID; "Rechnungsnummer12345"
  stays rejected. Confirm '#' counts as the separator in "Invoice #12345"
  (keyword regex already consumes it).

- [ ] test_version_consistency.py::test_plugin_version_matches_package_metadata
  (roadmap:df05) — package metadata (pyproject) is the canonical version;
  PLUGIN_VERSION becomes derived (importlib.metadata, plugin.yaml fallback).
  Side effect: filesystem-discovered dev checkouts report the last-synced
  metadata version, not an unsynced pyproject edit.
