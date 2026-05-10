"""Tests for convert.scrub() — retroactive stoplist entity cleanup."""

from __future__ import annotations

import frontmatter

from tests.conftest import make_store, make_md


def _entity(type_: str, value: str) -> dict:
    return {"type": type_, "value": value}


def _load_entities(path) -> list:
    return frontmatter.load(str(path)).metadata.get("entities", [])


# ---------------------------------------------------------------------------


def test_scrub_drops_stoplist_entities(tmp_path):
    """Entities with stoplist values are removed; clean entities survive."""
    from convert import scrub

    store = make_store(tmp_path)
    md = make_md(
        store / "notes", "doc.md",
        body="Hello world",
        entities=[
            _entity("person", "Subject"),
            _entity("person", "Alice Smith"),
            _entity("loc", "Thread"),
            _entity("org", "PayPal"),
            _entity("person", "Re"),
        ],
    )

    stats = scrub(store, {}, dry_run=False)

    assert stats["files_scanned"] >= 1
    assert stats["files_changed"] == 1
    assert stats["entities_removed"] == 3  # Subject, Thread, Re

    remaining = _load_entities(md)
    values = [e["value"] for e in remaining]
    assert "Alice Smith" in values
    assert "PayPal" in values
    assert "Subject" not in values
    assert "Thread" not in values
    assert "Re" not in values


def test_scrub_preserves_other_frontmatter_fields(tmp_path):
    """Tags, date, source and other frontmatter survive scrub untouched."""
    from convert import scrub

    store = make_store(tmp_path)
    md = make_md(
        store / "notes", "doc.md",
        body="Hello",
        source="imap",
        tags=["bill", "electricity"],
        date="2026-05-10",
        entities=[_entity("person", "Subject")],
    )

    scrub(store, {}, dry_run=False)

    post = frontmatter.load(str(md))
    assert post.metadata["source"] == "imap"
    assert post.metadata["tags"] == ["bill", "electricity"]
    assert post.metadata["date"] == "2026-05-10"


def test_scrub_idempotent(tmp_path):
    """Second --apply run reports files_changed=0 and entities_removed=0."""
    from convert import scrub

    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Hello",
        entities=[
            _entity("person", "Subject"),
            _entity("person", "Alice Smith"),
        ],
    )

    scrub(store, {}, dry_run=False)
    stats2 = scrub(store, {}, dry_run=False)

    assert stats2["files_changed"] == 0
    assert stats2["entities_removed"] == 0


def test_scrub_dry_run_does_not_write(tmp_path):
    """dry_run=True reports changes without modifying files."""
    from convert import scrub

    store = make_store(tmp_path)
    md = make_md(
        store / "notes", "doc.md",
        body="Hello",
        entities=[_entity("person", "Subject"), _entity("person", "Alice")],
    )
    original_text = md.read_text(encoding="utf-8")

    stats = scrub(store, {}, dry_run=True)

    assert stats["files_changed"] == 1
    assert stats["entities_removed"] == 1
    assert md.read_text(encoding="utf-8") == original_text
