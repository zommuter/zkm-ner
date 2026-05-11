"""Tests for zkm_ner.textfilter — N9b: markdown pre-strip + header stoplist; N9c: commonnoun stoplist."""

import pytest

from zkm_ner._types import Entity
from zkm_ner.textfilter import drop_commonnoun_stoplist, drop_stoplist, strip_markdown_artefacts


# ---------------------------------------------------------------------------
# strip_markdown_artefacts
# ---------------------------------------------------------------------------

def test_strip_separator_rows():
    body = "| Name | Age |\n|---|---|\n| Alice | 30 |\n"
    result = strip_markdown_artefacts(body)
    assert "|---|---|" not in result
    assert "| Name | Age |" in result
    assert "| Alice | 30 |" in result


def test_strip_pure_pipe_rows():
    body = "| |\n| | |\nsome text\n"
    result = strip_markdown_artefacts(body)
    assert "| |" not in result
    assert "some text" in result


def test_preserves_data_rows():
    body = "| From | alice@example.com |\n|------|---|\n| To | bob@example.com |\n"
    result = strip_markdown_artefacts(body)
    assert "alice@example.com" in result
    assert "bob@example.com" in result


# ---------------------------------------------------------------------------
# drop_stoplist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("word", [
    "From", "To", "Cc", "Bcc", "Subject", "Betreff",
    "Date", "Sent", "Received", "Thread", "Re", "Fwd", "Wg", "Aw",
])
def test_drop_stoplist_removes_header_words(word):
    entities = [Entity(type="person", value=word)]
    assert drop_stoplist(entities) == []


def test_drop_stoplist_case_insensitive():
    entities = [Entity(type="person", value="FROM"), Entity(type="person", value="subject")]
    assert drop_stoplist(entities) == []


def test_drop_stoplist_no_substring_false_positive():
    """Words that contain stoplist tokens but are longer must not be dropped."""
    entities = [
        Entity(type="person", value="Reginald"),
        Entity(type="org", value="Forward GmbH"),
        Entity(type="person", value="Tobias"),
    ]
    result = drop_stoplist(entities)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# drop_commonnoun_stoplist (N9c-2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("word", [
    "Du", "wünschen", "Zeit",
    "EUR", "CHF",
    "UTC", "MESZ", "CEST",
    "Internet", "CV", "AGB", "HRB",
])
def test_drop_commonnoun_stoplist_removes_known_words(word):
    entities = [Entity(type="person", value=word)]
    assert drop_commonnoun_stoplist(entities) == []


def test_drop_commonnoun_stoplist_case_insensitive():
    entities = [Entity(type="misc", value="eur"), Entity(type="misc", value="UTC")]
    assert drop_commonnoun_stoplist(entities) == []


def test_drop_commonnoun_stoplist_no_substring_false_positive():
    """'Zeitgeist' contains 'zeit' but must not be dropped."""
    entities = [Entity(type="misc", value="Zeitgeist")]
    assert drop_commonnoun_stoplist(entities) == [entities[0]]


def test_drop_commonnoun_stoplist_keeps_proper_nouns():
    entities = [
        Entity(type="person", value="Alice"),
        Entity(type="org", value="Alphabet Inc"),
    ]
    result = drop_commonnoun_stoplist(entities)
    assert len(result) == 2
