"""Spec tests for roadmap:b081 — accept lowercase/mixed-case IBANs.

IBANs typed casually in email bodies are often lowercase; the extractor regex
currently requires uppercase. ``value`` keeps raw casing; ``canonical`` is the
uppercase compact form (``zkm.canonical.iban`` already uppercases); the mod-97
checksum must be computed on the uppercased compact string so ``valid`` stays
correct. See ROADMAP.md id:b081.
"""

from __future__ import annotations

from zkm_ner.patterns import extract_ibans

# DE89 3704 0044 0532 0130 00 is the ISO 13616 example IBAN (checksum-valid).
_LOWER_SPACED = "de89 3704 0044 0532 0130 00"
_CANONICAL = "DE89370400440532013000"


def test_lowercase_iban_extracted():  # roadmap:b081
    ents = extract_ibans(f"iban: {_LOWER_SPACED} bitte verwenden")
    assert len(ents) == 1
    assert ents[0].value == _LOWER_SPACED


def test_lowercase_iban_checksum_valid():  # roadmap:b081
    """mod-97 must run on the uppercased compact form, not the raw lowercase."""
    ents = extract_ibans(f"Konto {_LOWER_SPACED} (privat)")
    assert len(ents) == 1
    assert ents[0].valid is True
    assert ents[0].canonical == _CANONICAL


def test_mixed_case_iban_canonical_uppercase():  # roadmap:b081
    ents = extract_ibans("Bitte an De89370400440532013000 zahlen.")
    assert len(ents) == 1
    assert ents[0].canonical == _CANONICAL
    assert ents[0].valid is True


def test_model_version_bumped_for_iban_case():  # roadmap:b081
    """Output distribution changes → iban-v1 must become iban-v2 in the key."""
    from zkm_ner.version import model_version

    ver = model_version("spacy")
    assert "iban-v2" in ver
    assert "iban-v1" not in ver
