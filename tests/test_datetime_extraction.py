"""Tests for γ type:datetime extraction — N-datetime L1.

Contract: relative-date fixture in a doc with a known ``date`` resolves
to the correct ISO 8601 canonical.  See docs/meeting-notes/2026-06-01-1334-contacts-calendar-plugins.md.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from zkm_ner.datetime_canon import canonicalise


# ---------------------------------------------------------------------------
# datetime_canon.canonicalise
# ---------------------------------------------------------------------------

class TestCanonicalise:
    def test_absolute_iso_date(self) -> None:
        assert canonicalise("2026-06-15") == "2026-06-15"

    def test_absolute_english_date(self) -> None:
        result = canonicalise("June 30, 2026")
        assert result == "2026-06-30"

    def test_absolute_german_date(self) -> None:
        result = canonicalise("30. Juni 2026")
        assert result == "2026-06-30"

    def test_relative_thursday_anchored(self) -> None:
        # Monday 2026-06-01 → next Thursday = 2026-06-04
        base = date(2026, 6, 1)
        result = canonicalise("Thursday", relative_base=base)
        assert result == "2026-06-04"

    def test_relative_german_day_anchored(self) -> None:
        # Same as above but German word
        base = date(2026, 6, 1)
        result = canonicalise("Donnerstag", relative_base=base)
        assert result == "2026-06-04"

    def test_relative_tomorrow_anchored(self) -> None:
        base = date(2026, 6, 1)
        result = canonicalise("morgen", relative_base=base)
        assert result == "2026-06-02"

    def test_unparseable_returns_none(self) -> None:
        result = canonicalise("not a date at all xyzzy")
        assert result is None

    def test_unknown_language_does_not_raise(self) -> None:
        # 'no' (Norwegian) and other unsupported codes must not raise ValueError
        result = canonicalise("2026-06-15", lang="no")
        assert result == "2026-06-15"

    def test_datetime_anchor(self) -> None:
        # Pass datetime instead of date — should still work
        base = datetime(2026, 6, 1, 10, 0)
        result = canonicalise("Thursday", relative_base=base)
        assert result == "2026-06-04"


# ---------------------------------------------------------------------------
# extract() produces datetime entities from spaCy DATE spans (EN model)
# ---------------------------------------------------------------------------

class TestExtractDatetime:
    def test_absolute_date_in_en_body(self) -> None:
        from zkm_ner.extract import extract

        body = "The deadline is June 30, 2026. Please comply."
        entities = extract(body, lang="en")
        datetime_ents = [e for e in entities if e.type == "datetime"]
        assert len(datetime_ents) >= 1
        found = datetime_ents[0]
        # canonical should be ISO 8601
        assert found.canonical == "2026-06-30" or found.value == "2026-06-30"
        assert found.standard == "ISO 8601"

    def test_relative_date_resolved_against_doc_date(self) -> None:
        from zkm_ner.extract import extract

        body = "The meeting is on Thursday."
        doc_date = date(2026, 6, 1)  # Monday
        entities = extract(body, lang="en", doc_date=doc_date)
        datetime_ents = [e for e in entities if e.type == "datetime"]
        assert len(datetime_ents) >= 1
        # canonical = 2026-06-04 (next Thursday from 2026-06-01)
        canon = datetime_ents[0].canonical or datetime_ents[0].value
        assert canon == "2026-06-04"

    def test_datetime_entity_has_body_scope(self) -> None:
        from zkm_ner.extract import extract

        body = "Deadline: June 30, 2026."
        entities = extract(body, lang="en")
        for e in entities:
            if e.type == "datetime":
                assert e.scope == "body"

    def test_no_datetime_without_date_span(self) -> None:
        from zkm_ner.extract import extract

        body = "Alice works at Acme Corp."
        entities = extract(body, lang="en")
        datetime_ents = [e for e in entities if e.type == "datetime"]
        assert len(datetime_ents) == 0
