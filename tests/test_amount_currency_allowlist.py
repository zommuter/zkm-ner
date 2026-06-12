"""Spec tests for roadmap:4352 — amount extractor must validate currency codes.

Any 3-uppercase-letter token followed/preceded by a number currently becomes an
``amount`` entity (`zkm.canonical.amount` does not validate codes, and core is
read-only from this plugin). The fix: an ISO 4217 allowlist (plus BTC/ETH)
applied in ``extract_amounts``. See ROADMAP.md id:4352, ARCHITECTURE.md §2.
"""

from __future__ import annotations

from zkm_ner.patterns import extract_amounts


def _amounts(body: str) -> list:
    return [e for e in extract_amounts(body) if e.type == "amount"]


# ---------------------------------------------------------------------------
# Non-currency 3-letter codes must be rejected
# ---------------------------------------------------------------------------


def test_din_standard_not_amount():  # roadmap:4352
    assert _amounts("Standard DIN 1045 applies to concrete.") == []


def test_iso_standard_not_amount():  # roadmap:4352
    assert _amounts("We are certified per ISO 9001 since long.") == []


def test_timezone_abbrev_not_amount():  # roadmap:4352
    assert _amounts("Treffen um 14 MEZ im Sitzungszimmer.") == []


# ---------------------------------------------------------------------------
# Real currencies keep working (asserted alongside a rejected sibling so each
# test exercises the allowlist boundary and is red pre-implementation)
# ---------------------------------------------------------------------------


def test_real_codes_still_extracted_prefix():  # roadmap:4352
    ents = _amounts("Offerte: CHF 250.00, Norm DIN 1045.")
    assert [e.unit for e in ents] == ["CHF"]
    assert ents[0].value == "CHF 250.00"


def test_real_codes_still_extracted_suffix():  # roadmap:4352
    ents = _amounts("Betrag 99.50 EUR, Treffen um 14 MEZ.")
    assert [e.unit for e in ents] == ["EUR"]
    assert ents[0].value == "99.50 EUR"


def test_crypto_tickers_allowed():  # roadmap:4352
    ents = _amounts("Paid 0.5 BTC, certified ISO 9001.")
    assert [e.unit for e in ents] == ["BTC"]


# ---------------------------------------------------------------------------
# Cache-key bump
# ---------------------------------------------------------------------------


def test_model_version_bumped_for_amount_allowlist():  # roadmap:4352
    """Output distribution changes → an amount-v2 component must enter the key."""
    from zkm_ner.version import model_version

    assert "amount-v2" in model_version("spacy")
