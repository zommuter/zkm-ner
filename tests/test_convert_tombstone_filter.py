# roadmap:fa5a
"""Spec tests for roadmap:fa5a — convert filters the cached entity set through
tombstones and emits the filtered set declaratively via ``emit_set``.

Decision D1 (zkm meeting 2026-06-23-1807): the extraction cache stays
immutable / single-writer (scrub must NOT rewrite cache entries — that breaks
idempotence-by-construction). Instead ``convert`` reads the cached set, drops any
entity whose ``(scope, type, value)`` triple is tombstoned (id:0566), and asserts
the filtered set with ``emit_set`` (mode="set") instead of legacy ``emit``. The core
``_retractable_values`` then clears the resurrected values from frontmatter.

DEPENDS ON roadmap:29ac — core must add ``"entities"`` to ``zkm.amendments._SET_FIELDS``
for the declarative set-retraction to apply to the entities field. Until 29ac lands,
``emit_set`` on entities is a no-op for retraction (it won't diff/drop), so the
resurrection-prevention assertion here cannot pass.

Currently RED: convert calls ``emit`` (not ``emit_set``) and does not consult tombstones,
so a cache-hit re-emits the stale set and union-merge resurrects the scrubbed value.
"""

from __future__ import annotations

from unittest.mock import patch

import frontmatter

from tests.conftest import make_store, make_md


def _entity(type_: str, value: str, scope: str | None = None) -> dict:
    d = {"type": type_, "value": value}
    if scope is not None:
        d["scope"] = scope
    return d


class _Stub:
    def __init__(self, type_, value):
        self.type, self.value, self.scope = type_, value, None

    def as_dict(self):
        d = {"type": self.type, "value": self.value}
        if self.scope:
            d["scope"] = self.scope
        return d


# ---------------------------------------------------------------------------
# convert emits declaratively (emit_set), not legacy emit
# ---------------------------------------------------------------------------

def test_convert_uses_emit_set_for_entities(tmp_path):
    """convert emits the entities field via emit_set (mode='set'), not legacy emit."""
    store = make_store(tmp_path)
    make_md(store / "notes", "doc.md", body="Alice Smith visited Berlin.")

    with (
        patch("zkm_ner.extract.extract", return_value=[_Stub("person", "Alice Smith")]),
        patch("zkm_ner.convert.emit_set") as mock_emit_set,
        patch("zkm_ner.convert.emit") as mock_emit,
    ):
        from convert import convert
        convert(store, {})

    assert mock_emit_set.called, "convert must use emit_set for the entities field"
    assert not mock_emit.called, "convert must not use legacy emit for entities"


# ---------------------------------------------------------------------------
# Tombstones suppress resurrection (the actual bug)
# ---------------------------------------------------------------------------

def test_convert_filters_tombstoned_entity_from_emitted_set(tmp_path):
    """A tombstoned (scope,type,value) is dropped from the set convert emits,
    even on a cache HIT (the unchanged-body resurrection path)."""
    from zkm_ner.tombstone import TombstoneStore

    store = make_store(tmp_path)
    make_md(store / "notes", "doc.md", body="Subject and Alice Smith.")

    extracted = [_Stub("person", "Subject"), _Stub("person", "Alice Smith")]

    captured = {}

    def _capture(store_path, *, key, fields, emitted_by, **kw):
        captured["fields"] = fields
        return store_path  # path-ish, unused

    # Tombstone "Subject" before the convert that re-extracts it.
    TombstoneStore(store).add("body", "person", "Subject")

    with (
        patch("zkm_ner.extract.extract", return_value=extracted),
        patch("zkm_ner.convert.emit_set", side_effect=_capture),
    ):
        from convert import convert
        convert(store, {})

    emitted_values = {e["value"] for e in captured["fields"]["entities"]}
    assert "Subject" not in emitted_values, "tombstoned value must be filtered out"
    assert "Alice Smith" in emitted_values, "non-tombstoned value must survive"


def test_scrub_then_full_sweep_does_not_resurrect(tmp_path):
    """End-to-end: scrub removes an entity, a subsequent full-sweep convert on the
    unchanged store does NOT re-add it to frontmatter (the D1 acceptance criterion)."""
    from convert import convert, scrub
    from zkm.amendments import apply_queue

    store = make_store(tmp_path)
    md = make_md(
        store / "notes", "doc.md",
        body="Subject and Alice Smith.",
        entities=[_entity("person", "Subject"), _entity("person", "Alice Smith")],
    )

    # scrub removes the stoplist value "Subject" and writes a tombstone.
    scrub(store, {}, dry_run=False)
    after_scrub = {e["value"] for e in frontmatter.load(str(md)).metadata.get("entities", [])}
    assert "Subject" not in after_scrub

    # A full-sweep convert re-extracts the same body (cache hit) and must NOT
    # resurrect the scrubbed value through union-merge.
    with patch("zkm_ner.extract.extract",
               return_value=[_Stub("person", "Subject"), _Stub("person", "Alice Smith")]):
        convert(store, {})
    apply_queue(store)

    final = {e["value"] for e in frontmatter.load(str(md)).metadata.get("entities", [])}
    assert "Subject" not in final, "scrubbed entity resurrected by convert's cached set"
    assert "Alice Smith" in final
