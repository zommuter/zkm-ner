"""Tests for zkm_ner.textfilter — N9b: markdown pre-strip + header stoplist; N9c: commonnoun stoplist; N9c-8: structural artefacts; N9c-10: section link artefacts; N9f: salutation blocklist; user-names runtime config."""

import pytest

from zkm_ner._types import Entity
from zkm_ner.textfilter import build_user_salutations, drop_commonnoun_stoplist, drop_salutation_blocklist, drop_section_link_artefacts, drop_stoplist, drop_structural_artefacts, strip_markdown_artefacts


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
        Entity(type="person", value="Maxine"),
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
    "Hallo Maxine",
    "hallo maxine",
    "HALLO MAXINE",
    "Hallo Maxine Mustermann",
    "Hello Maxine",
    "Hallo Herr Mustermann",
    "Hallo Herr",
    "Guten Tag Herr Mustermann",
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
        Entity(type="person", value="Hallo Maxine"),
        Entity(type="org", value="Best Regards"),
        Entity(type="misc", value="Du Dich"),
    ]
    assert drop_salutation_blocklist(entities) == []


def test_drop_salutation_blocklist_keeps_real_names():
    """Real person names and orgs must survive."""
    real = [
        Entity(type="person", value="Maxine Mustermann"),
        Entity(type="person", value="John F. Kennedy"),
        Entity(type="org", value="Humble Bundle"),
        Entity(type="org", value="Google"),
    ]
    assert drop_salutation_blocklist(real) == real


def test_drop_salutation_blocklist_empty_list():
    assert drop_salutation_blocklist([]) == []


# ---------------------------------------------------------------------------
# build_user_salutations + drop_salutation_blocklist extra kwarg (user-names feature)
# ---------------------------------------------------------------------------

def test_build_user_salutations_returns_greeting_phrase_set():
    """build_user_salutations(['Tobias', 'Kienzler']) generates 'hallo tobias' and 'guten tag herr kienzler'."""
    sal = build_user_salutations(["Tobias", "Kienzler"])
    assert "hallo tobias" in sal
    assert "hello tobias" in sal
    assert "guten tag herr kienzler" in sal
    assert "sehr geehrter herr kienzler" in sal


def test_build_user_salutations_bare_names_not_in_set():
    """Bare names must never be in the output — only prefix+name pairs."""
    sal = build_user_salutations(["Tobias", "Kienzler"])
    assert "tobias" not in sal
    assert "kienzler" not in sal


def test_build_user_salutations_accepts_string_input():
    """Comma-separated or newline-separated string input is also accepted (hand-edited YAML)."""
    sal_comma = build_user_salutations("Tobias, Kienzler")
    sal_newline = build_user_salutations("Tobias\nKienzler")
    assert "hallo tobias" in sal_comma
    assert "hallo kienzler" in sal_comma
    assert sal_comma == sal_newline


def test_build_user_salutations_empty_input():
    """Empty, None, empty-list, and blank-string inputs all return an empty frozenset."""
    assert build_user_salutations(None) == frozenset()
    assert build_user_salutations([]) == frozenset()
    assert build_user_salutations("") == frozenset()
    assert build_user_salutations(["", "  "]) == frozenset()


def test_build_user_salutations_normalises_whitespace():
    """Internal whitespace in multi-word names is normalised; leading/trailing stripped."""
    sal = build_user_salutations(["  Tobias  Kienzler  "])
    assert "hallo tobias kienzler" in sal


def test_drop_salutation_blocklist_extra_removes_user_greeting():
    """With extra= set, user-specific greetings are removed in addition to the static list."""
    user_sal = build_user_salutations(["Tobias"])
    entities = [
        Entity(type="person", value="Hallo Tobias"),
        Entity(type="person", value="Hello Tobias"),
        Entity(type="person", value="Tobias Kienzler"),  # legit — bare full name
        Entity(type="person", value="Best Regards"),     # static blocklist entry
    ]
    result = drop_salutation_blocklist(entities, extra=user_sal)
    values = [e.value for e in result]
    assert "Hallo Tobias" not in values
    assert "Hello Tobias" not in values
    assert "Best Regards" not in values
    assert "Tobias Kienzler" in values  # bare full name survives


def test_drop_salutation_blocklist_no_extra_unchanged_behaviour():
    """Calling without extra= preserves the original static-blocklist-only behaviour."""
    entities = [
        Entity(type="person", value="Hallo Tobias"),  # NOT in static list
        Entity(type="person", value="Hallo Maxine"),  # IS in static list
    ]
    result = drop_salutation_blocklist(entities)
    values = [e.value for e in result]
    assert "Hallo Tobias" in values     # not filtered without extra=
    assert "Hallo Maxine" not in values  # static entry still filtered


# ---------------------------------------------------------------------------
# drop_section_link_artefacts (N9c-10 — class 7 pollution)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "Section 2]",
    "Section 3]\n\n",
    "Section 5]\n\n++ Section 6",
    "Section 6]\n\n++ Footer\n\nSocial Media",
    "Section 10]",
])
def test_drop_section_link_artefacts_removes_artifacts(value):
    """Class 7: broken markdown link-target fragments starting with 'Section N]'."""
    entities = [Entity(type="misc", value=value)]
    assert drop_section_link_artefacts(entities) == []


def test_drop_section_link_artefacts_keeps_legitimate_references():
    """Section references without closing bracket are ambiguous — must not be dropped."""
    real = [
        Entity(type="misc", value="Section 1"),
        Entity(type="misc", value="Section 101"),
        Entity(type="misc", value="Section 5.1 & 6.5"),
        Entity(type="org", value="Google"),
    ]
    assert drop_section_link_artefacts(real) == real


def test_drop_section_link_artefacts_empty_list():
    assert drop_section_link_artefacts([]) == []
