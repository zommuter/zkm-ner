"""Tests for extract_ibans — E7 IBAN value-type extractor."""

from __future__ import annotations

from zkm_ner.patterns import _mod97, extract_ibans, extract_all


# ---------------------------------------------------------------------------
# Known-valid test IBANs
# ---------------------------------------------------------------------------

# German test IBAN (from canonical.py docstring and ISO 13616 examples)
_DE_IBAN_COMPACT = "DE89370400440532013000"
_DE_IBAN_SPACED = "DE89 3704 0044 0532 0130 00"
_DE_IBAN_HYPHEN = "DE89-3704-0044-0532-0130-00"

# UK test IBAN (ISO 13616 / Wikipedia example)
_GB_IBAN_COMPACT = "GB82WEST12345698765432"


# ---------------------------------------------------------------------------
# mod-97 checksum
# ---------------------------------------------------------------------------

def test_mod97_valid_german() -> None:
    assert _mod97(_DE_IBAN_COMPACT) == 1


def test_mod97_valid_uk() -> None:
    assert _mod97(_GB_IBAN_COMPACT) == 1


def test_mod97_invalid_returns_not_one() -> None:
    corrupted = "DE99370400440532013000"  # check digits changed
    assert _mod97(corrupted) != 1


# ---------------------------------------------------------------------------
# extract_ibans — basic correctness
# ---------------------------------------------------------------------------

def test_compact_iban() -> None:
    ents = extract_ibans(f"IBAN: {_DE_IBAN_COMPACT}")
    assert len(ents) == 1
    e = ents[0]
    assert e.type == "iban"
    assert e.value == _DE_IBAN_COMPACT
    assert e.canonical is None  # already compact, canonical == value → omitted
    assert e.standard == "ISO 13616"
    assert e.valid is True


def test_spaced_iban_canonical_differs() -> None:
    ents = extract_ibans(f"Konto: {_DE_IBAN_SPACED}.")
    assert len(ents) == 1
    e = ents[0]
    assert e.value == _DE_IBAN_SPACED
    assert e.canonical == _DE_IBAN_COMPACT
    assert e.valid is True


def test_hyphenated_iban() -> None:
    ents = extract_ibans(f"IBAN: {_DE_IBAN_HYPHEN}")
    assert len(ents) == 1
    e = ents[0]
    assert e.canonical == _DE_IBAN_COMPACT
    assert e.valid is True


def test_uk_iban_compact() -> None:
    ents = extract_ibans(f"Send to {_GB_IBAN_COMPACT} please.")
    assert len(ents) == 1
    e = ents[0]
    assert e.value == _GB_IBAN_COMPACT
    assert e.valid is True


def test_invalid_checksum_marked_false() -> None:
    corrupted = "DE99370400440532013000"
    ents = extract_ibans(corrupted)
    assert len(ents) == 1
    assert ents[0].valid is False
    assert ents[0].standard == "ISO 13616"


def test_multiple_ibans_in_body() -> None:
    body = f"From {_DE_IBAN_COMPACT} to {_GB_IBAN_COMPACT}."
    ents = extract_ibans(body)
    assert len(ents) == 2
    values = {e.value for e in ents}
    assert _DE_IBAN_COMPACT in values
    assert _GB_IBAN_COMPACT in values


# ---------------------------------------------------------------------------
# Boundary — must NOT match inside longer tokens
# ---------------------------------------------------------------------------

def test_no_match_preceded_by_alpha() -> None:
    ents = extract_ibans(f"XYZ{_DE_IBAN_COMPACT}")
    assert len(ents) == 0


def test_no_match_preceded_by_digit() -> None:
    ents = extract_ibans(f"1{_DE_IBAN_COMPACT}")
    assert len(ents) == 0


def test_no_match_empty_body() -> None:
    assert extract_ibans("") == []


def test_no_iban_in_plain_text() -> None:
    assert extract_ibans("Hello, please pay the invoice.") == []


# ---------------------------------------------------------------------------
# Length gate — too short (< 15 compact chars) not emitted
# ---------------------------------------------------------------------------

def test_too_short_not_matched() -> None:
    # 4 header + 10 BBAN = 14 compact chars — below minimum
    ents = extract_ibans("DE890123456789")
    assert len(ents) == 0


# ---------------------------------------------------------------------------
# Offsets
# ---------------------------------------------------------------------------

def test_start_end_offsets() -> None:
    body = f"IBAN: {_DE_IBAN_COMPACT} — done"
    ents = extract_ibans(body)
    assert len(ents) == 1
    e = ents[0]
    assert body[e.start:e.end] == _DE_IBAN_COMPACT


# ---------------------------------------------------------------------------
# Integration: extract_all includes IBANs
# ---------------------------------------------------------------------------

def test_extract_all_includes_iban() -> None:
    body = f"Please wire to {_DE_IBAN_COMPACT}."
    ents = extract_all(body)
    iban_ents = [e for e in ents if e.type == "iban"]
    assert len(iban_ents) == 1
    assert iban_ents[0].value == _DE_IBAN_COMPACT
