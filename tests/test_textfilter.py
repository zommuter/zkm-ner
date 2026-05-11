"""Tests for zkm_ner.textfilter — N9b: markdown pre-strip + header stoplist; N9c: commonnoun stoplist; N9c-8: structural artefacts; N9f: salutation blocklist."""

import pytest

from zkm_ner._types import Entity
from zkm_ner.textfilter import drop_commonnoun_stoplist, drop_salutation_blocklist, drop_stoplist, drop_structural_artefacts, strip_markdown_artefacts


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


# ---------------------------------------------------------------------------
# drop_structural_artefacts (N9c-8)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["| |", "| | |", "|  |", "||", " | ", "|"])
def test_drop_structural_artefacts_removes_pipe_whitespace(value):
    """Pilot class 5: inline empty table cells composed of pipes and whitespace only."""
    entities = [Entity(type="person", value=value)]
    assert drop_structural_artefacts(entities) == []


def test_drop_structural_artefacts_keeps_real_values():
    """Values with letters or digits must not be dropped."""
    entities = [
        Entity(type="person", value="Alice"),
        Entity(type="org", value="| Alice |"),
        Entity(type="misc", value="SBB"),
    ]
    assert drop_structural_artefacts(entities) == entities


def test_drop_structural_artefacts_empty_list():
    assert drop_structural_artefacts([]) == []


# ---------------------------------------------------------------------------
# drop_salutation_blocklist (N9f — class 6 pollution)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "Hallo Tobias",
    "hallo tobias",
    "HALLO TOBIAS",
    "Hallo Tobias Kienzler",
    "Hello Tobias",
    "Hallo Herr Kienzler",
    "Hallo Herr",
    "Guten Tag Herr Kienzler",
    "Guten Tag Herr",
    "Lieber Herr",
    "Du Dich",
    "Wenn Sie",
    "Best Regards",
    "best regards",
    "Kind Regards",
    "Mit freundlichen Grüßen",
    "Viele Grüße",
    "Mit besten Grüßen",
])
def test_drop_salutation_blocklist_removes_known_phrases(value):
    entities = [Entity(type="person", value=value)]
    assert drop_salutation_blocklist(entities) == []


def test_drop_salutation_blocklist_type_agnostic():
    """Blocklist is type-agnostic — should drop PERSON, ORG, MISC variants."""
    entities = [
        Entity(type="person", value="Hallo Tobias"),
        Entity(type="org", value="Best Regards"),
        Entity(type="misc", value="Du Dich"),
    ]
    assert drop_salutation_blocklist(entities) == []


def test_drop_salutation_blocklist_keeps_real_names():
    """Real person names and orgs must survive."""
    real = [
        Entity(type="person", value="Tobias Kienzler"),
        Entity(type="person", value="John F. Kennedy"),
        Entity(type="org", value="Humble Bundle"),
        Entity(type="org", value="Google"),
    ]
    assert drop_salutation_blocklist(real) == real


def test_drop_salutation_blocklist_empty_list():
    assert drop_salutation_blocklist([]) == []
