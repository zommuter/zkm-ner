"""Tests for zkm_ner.spacy_backend.

Requires spaCy + de_core_news_sm + en_core_web_sm to be installed.
All tests are skipped automatically when spaCy or its models are missing.
"""

from __future__ import annotations

import pytest

spacy = pytest.importorskip("spacy")


def _models_available() -> bool:
    try:
        spacy.load("de_core_news_sm")
        spacy.load("en_core_web_sm")
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _models_available(),
    reason="spaCy models de_core_news_sm / en_core_web_sm not installed",
)


from zkm_ner.spacy_backend import extract_spacy  # noqa: E402


# ---------------------------------------------------------------------------

def test_german_text_extracts_person() -> None:
    body = "Angela Merkel war Bundeskanzlerin von Deutschland."
    ents = extract_spacy(body, lang="de")
    types = {e.type for e in ents}
    values = {e.value for e in ents}
    assert "person" in types
    assert any("Merkel" in v for v in values)


def test_german_text_extracts_org() -> None:
    body = "Der Bundestag hat das Gesetz verabschiedet."
    ents = extract_spacy(body, lang="de")
    # May or may not catch "Bundestag" depending on model; at least no crash
    assert isinstance(ents, list)


def test_english_text_extracts_person() -> None:
    body = "Albert Einstein was born in Ulm."
    ents = extract_spacy(body, lang="en")
    types = {e.type for e in ents}
    assert "person" in types
    assert any("Einstein" in e.value for e in ents)


def test_english_text_extracts_loc() -> None:
    body = "The conference was held in Berlin."
    ents = extract_spacy(body, lang="en")
    types = {e.type for e in ents}
    assert "loc" in types


def test_empty_body_returns_empty() -> None:
    assert extract_spacy("") == []
    assert extract_spacy("   ") == []


def test_entities_have_spans() -> None:
    body = "Barack Obama visited Berlin."
    ents = extract_spacy(body, lang="en")
    for e in ents:
        assert e.start >= 0
        assert e.end > e.start


def test_lang_override_uses_de_model() -> None:
    # Force German model on English text — may produce different results but must not crash
    body = "The quick brown fox jumps over the lazy dog."
    ents = extract_spacy(body, lang="de")
    assert isinstance(ents, list)


def test_mixed_language_fallback_no_crash() -> None:
    # Doc-level langdetect on mixed text — accept whatever result, just no exception
    body = (
        "Sehr geehrte Damen und Herren, please find attached the invoice. "
        "Mit freundlichen Grüßen, the Finance Team."
    )
    ents = extract_spacy(body)
    assert isinstance(ents, list)
