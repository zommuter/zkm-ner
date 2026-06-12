"""Spec tests for roadmap:2512 — invoice IDs glued to the keyword separator.

``_INVOICE_KEYWORD_RE`` requires trailing whitespace after the optional
punctuation (``(?:\\s*[:\\-=])?\\s+``), so the very common ``Invoice #12345``
and ``Rechnungsnummer:12345`` forms are missed. The fix: require at least one
separator character (whitespace OR ``:-=#``-class punctuation), with or without
trailing space — but a keyword glued directly to digits with NO separator at
all must still be rejected. See ROADMAP.md id:2512.
"""

from __future__ import annotations

from zkm_ner.patterns import extract_invoice_ids


def test_invoice_hash_glued():  # roadmap:2512
    ents = extract_invoice_ids("Please find Invoice #12345 attached.")
    assert [e.value for e in ents] == ["12345"]


def test_rechnungsnummer_colon_glued():  # roadmap:2512
    ents = extract_invoice_ids("Rechnungsnummer:RG-2026-0042 vom 12.06.2026")
    assert [e.value for e in ents] == ["RG-2026-0042"]


def test_no_separator_still_rejected():  # roadmap:2512
    """GUARD (green pre-implementation): keyword glued directly to the ID with
    no separator stays a non-match — protects against an over-broad regex fix."""
    assert extract_invoice_ids("Rechnungsnummer12345 ist keine Referenz.") == []


def test_model_version_bumped_for_invoice_separator():  # roadmap:2512
    """Output distribution changes → invoice-v1 must become invoice-v2 in the key."""
    from zkm_ner.version import model_version

    ver = model_version("spacy")
    assert "invoice-v2" in ver
    assert "invoice-v1" not in ver
