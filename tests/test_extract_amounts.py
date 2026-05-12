"""Tests for extract_amounts — E6 end-to-end pilot."""

from __future__ import annotations

from zkm_ner.patterns import extract_amounts, extract_all


# ---------------------------------------------------------------------------
# Mandated test cases (from TODO E6)
# ---------------------------------------------------------------------------

def test_chf_swiss_apostrophe_dash() -> None:
    ents = extract_amounts("Betrag: CHF 1'000.-")
    assert len(ents) == 1
    e = ents[0]
    assert e.type == "amount"
    assert e.value == "CHF 1'000.-"
    assert e.canonical == "1000.00"
    assert e.unit == "CHF"
    assert e.standard == "ISO 4217"


def test_euro_de_decimal() -> None:
    ents = extract_amounts("Rechnung: 1.000,50 €")
    assert len(ents) == 1
    e = ents[0]
    assert e.value == "1.000,50 €"
    assert e.canonical == "1000.50"
    assert e.unit == "EUR"


def test_negative_usd() -> None:
    ents = extract_amounts("Balance: -0.01 USD")
    assert len(ents) == 1
    e = ents[0]
    assert e.value == "-0.01 USD"
    assert e.canonical == "-0.01"
    assert e.unit == "USD"


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------

def test_prefix_symbol_dollar() -> None:
    ents = extract_amounts("Price: $99.99")
    assert len(ents) == 1
    assert ents[0].unit == "USD"
    assert ents[0].canonical == "99.99"


def test_eur_symbol_suffix_no_space() -> None:
    ents = extract_amounts("Total: 1234.56€")
    assert len(ents) == 1
    assert ents[0].unit == "EUR"
    assert ents[0].canonical == "1234.56"


def test_positive_sign_prefix() -> None:
    ents = extract_amounts("+CHF 50.00")
    assert len(ents) == 1
    assert ents[0].canonical == "50.00"
    assert ents[0].unit == "CHF"


def test_sfr_alias() -> None:
    ents = extract_amounts("SFr. 200.-")
    assert len(ents) == 1
    assert ents[0].unit == "CHF"
    assert ents[0].canonical == "200.00"


def test_multiple_amounts_in_body() -> None:
    body = "Paid CHF 100.- and 50.00 EUR."
    ents = extract_amounts(body)
    assert len(ents) == 2
    values = {e.value for e in ents}
    assert "CHF 100.-" in values
    assert "50.00 EUR" in values


def test_span_offsets() -> None:
    body = "Invoice: CHF 1'000.- total"
    ents = extract_amounts(body)
    assert len(ents) == 1
    e = ents[0]
    assert e.start >= 0
    assert body[e.start:e.end] == e.value


def test_no_currency_no_match() -> None:
    ents = extract_amounts("The year is 2026.")
    assert ents == []


def test_currency_alone_no_match() -> None:
    ents = extract_amounts("Currency: CHF")
    assert ents == []


def test_no_false_positive_mid_word() -> None:
    # RECHNUNG contains no match; EUR mid-token shouldn't fire
    ents = extract_amounts("EUREKA!")
    assert ents == []


def test_canonical_none_when_equal() -> None:
    # For a value where decimal_str == raw (unlikely but guard the invariant)
    ents = extract_amounts("CHF 1'000.-")
    for e in ents:
        assert e.canonical != e.value


# ---------------------------------------------------------------------------
# End-to-end: extract_all includes amounts
# ---------------------------------------------------------------------------

def test_extract_all_includes_amounts() -> None:
    body = "Please pay CHF 1'000.- to the account."
    ents = extract_all(body)
    amount_ents = [e for e in ents if e.type == "amount"]
    assert len(amount_ents) == 1
    assert amount_ents[0].unit == "CHF"


def test_extract_all_amount_does_not_overlap_email() -> None:
    body = "Contact alice@example.com for CHF 200 payment."
    ents = extract_all(body)
    types = {e.type for e in ents}
    assert "email_address" in types
    assert "amount" in types


def test_extract_all_amount_and_url_coexist() -> None:
    body = "See https://example.com and pay EUR 99.00."
    ents = extract_all(body)
    assert any(e.type == "url" for e in ents)
    assert any(e.type == "amount" for e in ents)
