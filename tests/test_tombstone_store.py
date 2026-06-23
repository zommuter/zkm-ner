# roadmap:0566
"""Spec tests for roadmap:0566 — scrub writes a per-store tombstone per removed entity.

Decision D1 (zkm meeting 2026-06-23-1807): scrub edits frontmatter but the extraction
cache keeps the removed entities, so the next full-sweep convert re-emits the stale set
and set-union merge resurrects the scrubbed value. The chosen mechanism is a per-store
tombstone keyed ``(scope, type, value)``: ``scrub(dry_run=False)`` records one tombstone
per removed entity. ``convert`` (id:fa5a) later filters the cached set through these
tombstones before emitting. NO tombstone-GC machinery until list growth is observed
(observe-first).

This file specs the STORE half (id:0566) only — the writer and the read API. The
convert-side filter + emit_set adoption is roadmap:fa5a.

Currently RED: there is no tombstone module / store, and scrub does not write one.
"""

from __future__ import annotations

import frontmatter

from tests.conftest import make_store, make_md


def _entity(type_: str, value: str, scope: str | None = None) -> dict:
    d = {"type": type_, "value": value}
    if scope is not None:
        d["scope"] = scope
    return d


# ---------------------------------------------------------------------------
# Store API: a per-store tombstone keyed (scope, type, value)
# ---------------------------------------------------------------------------

def test_tombstone_store_roundtrip(tmp_path):
    """A written tombstone is read back; the key is the (scope, type, value) triple."""
    from zkm_ner.tombstone import TombstoneStore

    store = make_store(tmp_path)
    ts = TombstoneStore(store)
    assert ts.is_tombstoned("body", "person", "Subject") is False

    ts.add("body", "person", "Subject")

    # Reopened (fresh instance) — persisted on disk, not just in memory.
    ts2 = TombstoneStore(store)
    assert ts2.is_tombstoned("body", "person", "Subject") is True


def test_tombstone_key_is_scope_type_value_specific(tmp_path):
    """Tombstoning one triple does not tombstone a different scope/type/value."""
    from zkm_ner.tombstone import TombstoneStore

    store = make_store(tmp_path)
    ts = TombstoneStore(store)
    ts.add("body", "person", "Subject")

    assert ts.is_tombstoned("body", "person", "Subject") is True
    assert ts.is_tombstoned("signature", "person", "Subject") is False  # scope differs
    assert ts.is_tombstoned("body", "org", "Subject") is False          # type differs
    assert ts.is_tombstoned("body", "person", "Alice") is False         # value differs


def test_tombstone_add_is_idempotent(tmp_path):
    """Adding the same triple twice does not duplicate it (set semantics)."""
    from zkm_ner.tombstone import TombstoneStore

    store = make_store(tmp_path)
    ts = TombstoneStore(store)
    ts.add("body", "person", "Subject")
    ts.add("body", "person", "Subject")

    triples = list(ts.all())
    assert triples.count(("body", "person", "Subject")) == 1


def test_tombstone_lives_under_zkm_state(tmp_path):
    """Tombstones are stored under the per-store .zkm-state/ dir (convention)."""
    from zkm_ner.tombstone import TombstoneStore

    store = make_store(tmp_path)
    ts = TombstoneStore(store)
    ts.add("body", "person", "Subject")

    state = store / ".zkm-state"
    assert state.is_dir()
    # Some file under .zkm-state now records the tombstone (exact path is an impl
    # detail; the contract is "persisted under .zkm-state").
    assert any(p.is_file() for p in state.rglob("*"))


# ---------------------------------------------------------------------------
# scrub writes a tombstone per removed entity (only on real runs)
# ---------------------------------------------------------------------------

def test_scrub_writes_tombstone_per_removed_entity(tmp_path):
    """scrub(dry_run=False) records a tombstone for each entity it removes."""
    from convert import scrub
    from zkm_ner.tombstone import TombstoneStore

    store = make_store(tmp_path)
    # "Subject" is a stoplist value (see test_scrub.py); a clean person survives.
    make_md(
        store / "notes", "doc.md",
        body="Hello world",
        entities=[_entity("person", "Subject"), _entity("person", "Alice Smith")],
    )

    scrub(store, {}, dry_run=False)

    ts = TombstoneStore(store)
    assert ts.is_tombstoned(None or "body", "person", "Subject") or \
        ts.is_tombstoned("body", "person", "Subject")
    # The surviving entity is NOT tombstoned.
    assert ts.is_tombstoned("body", "person", "Alice Smith") is False


def test_scrub_dry_run_writes_no_tombstone(tmp_path):
    """A dry-run scrub reports removals but must not write tombstones."""
    from convert import scrub
    from zkm_ner.tombstone import TombstoneStore

    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Hello world",
        entities=[_entity("person", "Subject")],
    )

    scrub(store, {}, dry_run=True)

    ts = TombstoneStore(store)
    assert list(ts.all()) == []


def test_scrub_tombstone_records_entity_scope(tmp_path):
    """A removed signature-scoped entity is tombstoned under its scope, not body."""
    from convert import scrub
    from zkm_ner.tombstone import TombstoneStore

    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Hello world",
        entities=[_entity("person", "Subject", scope="signature")],
    )

    scrub(store, {}, dry_run=False)

    ts = TombstoneStore(store)
    assert ts.is_tombstoned("signature", "person", "Subject") is True
    assert ts.is_tombstoned("body", "person", "Subject") is False
