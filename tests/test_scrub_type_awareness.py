"""Spec tests for roadmap:a1c2 — deterministic entity types must be exempt
from scrub/suspicious name-shape heuristics.

Deterministic types (pattern-overlay + datetime) are validated structurally at
extraction time; scrub's stoplists and isolated-POS gate were designed for
spaCy person/org/loc/misc false positives and must not second-guess them.
See ROADMAP.md id:a1c2 and ARCHITECTURE.md §6–7.
"""

from __future__ import annotations

import frontmatter

from tests.conftest import make_store, make_md


def _load_entities(path) -> list:
    return frontmatter.load(str(path)).metadata.get("entities", [])


# ---------------------------------------------------------------------------
# scrub() must not remove deterministic types via the isolated-POS gate
# ---------------------------------------------------------------------------


def test_scrub_keeps_datetime_relative_value(tmp_path):  # roadmap:a1c2
    """A datetime entity with a relative-word value survives scrub.

    'tomorrow' parses as NOUN in isolation, so the type-agnostic isolated-POS
    gate currently removes it — but the value was already validated by
    dateparser at extraction time (canonical present).
    """
    from convert import scrub

    store = make_store(tmp_path)
    md = make_md(
        store / "mail", "msg.md",
        body="The meeting is tomorrow.",
        entities=[
            {
                "scope": "body",
                "type": "datetime",
                "value": "tomorrow",
                "canonical": "2026-06-13",
                "standard": "ISO 8601",
            },
        ],
    )

    scrub(store, {}, dry_run=False)

    values = [e["value"] for e in _load_entities(md)]
    assert "tomorrow" in values, "scrub must not POS-drop validated datetime entities"


def test_scrub_keeps_german_datetime_value(tmp_path):  # roadmap:a1c2
    """German relative datetime 'morgen' (ADV in isolation) survives scrub."""
    from convert import scrub

    store = make_store(tmp_path)
    md = make_md(
        store / "mail", "msg.md",
        body="Wir sehen uns morgen.",
        entities=[
            {
                "scope": "body",
                "type": "datetime",
                "value": "morgen",
                "canonical": "2026-06-13",
                "standard": "ISO 8601",
            },
        ],
    )

    scrub(store, {}, dry_run=False)

    values = [e["value"] for e in _load_entities(md)]
    assert "morgen" in values


def test_scrub_keeps_pattern_type_with_stoplist_value(tmp_path):  # roadmap:a1c2
    """A keyword-anchored invoice_id whose value collides with the stoplist
    ('RE' ~ subject-line prefix 're') is kept — the stoplist targets NER types.
    """
    from convert import scrub

    store = make_store(tmp_path)
    md = make_md(
        store / "mail", "msg.md",
        body="Rechnungsnummer: RE",
        entities=[
            {"scope": "body", "type": "invoice_id", "value": "RE"},
        ],
    )

    scrub(store, {}, dry_run=False)

    values = [e["value"] for e in _load_entities(md)]
    assert "RE" in values, "stoplist must not apply to pattern-validated types"


def test_scrub_still_drops_ner_person_stoplist_value(tmp_path):  # roadmap:a1c2
    """NER-type heuristics are unchanged: person 'Subject' is still removed
    while a deterministic datetime sibling in the same file is kept.
    """
    from convert import scrub

    store = make_store(tmp_path)
    md = make_md(
        store / "mail", "msg.md",
        body="Subject line noise, meeting tomorrow.",
        entities=[
            {"scope": "body", "type": "person", "value": "Subject"},
            {
                "scope": "body",
                "type": "datetime",
                "value": "tomorrow",
                "canonical": "2026-06-13",
                "standard": "ISO 8601",
            },
        ],
    )

    stats = scrub(store, {}, dry_run=False)

    values = [e["value"] for e in _load_entities(md)]
    assert "Subject" not in values, "NER-type stoplist removal must keep working"
    assert "tomorrow" in values, "deterministic sibling must survive"
    assert stats["entities_removed"] == 1


# ---------------------------------------------------------------------------
# suspicious dispatch: datetime gets a no-suspicion entry
# ---------------------------------------------------------------------------


def test_suspicious_datetime_numeric_not_suspicious():  # roadmap:a1c2
    """Numeric datetime values must not fall back to the name predicate
    ('no alphabetic content') — canonicalisation already validated them.
    """
    from zkm_ner.suspicious import is_suspicious

    assert is_suspicious("datetime", "2026") is None


def test_suspicious_datetime_time_not_suspicious():  # roadmap:a1c2
    from zkm_ner.suspicious import is_suspicious

    assert is_suspicious("datetime", "14:30") is None
