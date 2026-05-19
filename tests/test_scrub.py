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


# ---------------------------------------------------------------------------
# N9c-4: commonnoun stoplist + isolated POS predicate in scrub
# ---------------------------------------------------------------------------


def test_scrub_drops_commonnoun_stoplist_entities(tmp_path):
    """Entities in _COMMONNOUN_STOPLIST (e.g. 'Du', 'EUR') are removed by scrub."""
    from convert import scrub

    store = make_store(tmp_path)
    md = make_md(
        store / "notes", "doc.md",
        body="Hello",
        entities=[
            _entity("person", "Du"),
            _entity("misc", "EUR"),
            _entity("person", "Alice Smith"),
        ],
    )

    stats = scrub(store, {}, dry_run=False)

    assert stats["files_changed"] == 1
    assert stats["entities_removed"] == 2
    remaining = _load_entities(md)
    values = [e["value"] for e in remaining]
    assert "Du" not in values
    assert "EUR" not in values
    assert "Alice Smith" in values


def test_scrub_isolated_pos_removes_common_noun(tmp_path):
    """Single-word common nouns not in the explicit stoplist are caught by isolated POS check."""
    from convert import scrub

    store = make_store(tmp_path)
    # 'Woche' is NOUN in German — spaCy should tag it as NOUN in isolation.
    # 'Alice' is PROPN — must survive.
    md = make_md(
        store / "notes", "doc.md",
        body="Hello",
        entities=[
            _entity("person", "Woche"),
            _entity("person", "Alice"),
        ],
    )

    stats = scrub(store, {}, dry_run=False)

    remaining = _load_entities(md)
    values = [e["value"] for e in remaining]
    assert "Woche" not in values
    assert "Alice" in values


def test_scrub_drops_structural_artefact_entities(tmp_path):
    """Entities with pipe-only values (e.g. '| |') are removed by scrub."""
    from convert import scrub

    store = make_store(tmp_path)
    md = make_md(
        store / "notes", "doc.md",
        body="Hello",
        entities=[
            _entity("person", "| |"),
            _entity("person", "| | |"),
            _entity("org", "PayPal"),
        ],
    )

    stats = scrub(store, {}, dry_run=False)

    assert stats["files_changed"] == 1
    assert stats["entities_removed"] == 2
    remaining = _load_entities(md)
    values = [e["value"] for e in remaining]
    assert "| |" not in values
    assert "| | |" not in values
    assert "PayPal" in values


def test_scrub_bilingual_pos_drops_english_common_words(tmp_path):
    """English words tagged PROPN/X by DE model are caught via EN model fallback.

    'Learn' (VERB in EN) and 'Link' (NOUN in EN) must be scrubbed even though
    the German model would classify both as PROPN.
    """
    from convert import scrub

    store = make_store(tmp_path)
    md = make_md(
        store / "notes", "doc.md",
        body="Hello",
        entities=[
            _entity("person", "Learn"),
            _entity("misc", "Link"),
            _entity("person", "Alice"),
            _entity("org", "Google"),
        ],
    )

    stats = scrub(store, {}, dry_run=False)

    assert stats["entities_removed"] == 2
    remaining = _load_entities(md)
    values = [e["value"] for e in remaining]
    assert "Learn" not in values
    assert "Link" not in values
    assert "Alice" in values
    assert "Google" in values


def test_scrub_pilot_dump_writes_jsonl_for_verifier_verdicts(tmp_path):
    """When pilot_dump_path is set and a verifier is active, verdicts are written to JSONL."""
    import json
    from unittest.mock import patch

    from convert import scrub

    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Some context",
        entities=[
            _entity("person", "klicken Sie"),  # suspicious: lowercase person
            _entity("org", "Swiss Federal Railways"),  # legit org, not suspicious
        ],
    )

    dump_path = tmp_path / "pilot.jsonl"

    def _fake_verify(value, type_, *, model, endpoint, api_key, context, cache):
        return "drop" if value == "klicken Sie" else "keep"

    with patch("zkm_ner.verifier.verify", side_effect=_fake_verify):
        stats = scrub(
            store, {},
            dry_run=True,
            with_verifier=True,
            pilot_dump_path=dump_path,
        )

    assert dump_path.exists()
    records = [json.loads(line) for line in dump_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1  # only the suspicious entity goes to verifier
    rec = records[0]
    assert rec["value"] == "klicken Sie"
    assert rec["type"] == "person"
    assert rec["verdict"] == "drop"
    assert rec["suspicious_reason"] is not None
    assert rec["is_control"] is False
    assert stats["pilot_records"] == 1
    # dry_run: file not modified
    remaining = _load_entities(store / "notes" / "doc.md")
    assert len(remaining) == 2


def test_scrub_isolated_pos_keeps_multiword(tmp_path):
    """Multi-word entities bypass the isolated POS check and are not removed."""
    from convert import scrub

    store = make_store(tmp_path)
    # 'Die Zeit' has 'Zeit' as a known common noun in isolation, but as a
    # multi-word entity it bypasses the POS predicate.
    md = make_md(
        store / "notes", "doc.md",
        body="Hello",
        entities=[_entity("org", "Die Zeit")],
    )

    stats = scrub(store, {}, dry_run=False)

    assert stats["entities_removed"] == 0
    remaining = _load_entities(md)
    assert any(e["value"] == "Die Zeit" for e in remaining)


# ---------------------------------------------------------------------------
# Resume / watermark / incremental pilot flush
# ---------------------------------------------------------------------------


def test_resume_after_file_skips_processed_files(tmp_path):
    """resume_after_file causes the plugin to skip files before the watermark."""
    from convert import scrub

    store = make_store(tmp_path)
    # Create 3 files, two with stale entities.
    make_md(store / "notes", "a.md", body="x", entities=[_entity("person", "Subject")])
    make_md(store / "notes", "b.md", body="x", entities=[_entity("person", "Subject")])
    make_md(store / "notes", "c.md", body="x", entities=[_entity("person", "Subject")])

    # Resume after b.md → only c.md should be processed.
    stats = scrub(store, {}, dry_run=False, resume_after_file="notes/b.md")

    assert stats["files_scanned"] == 1  # only c.md
    assert stats["files_changed"] == 1
    assert stats["entities_removed"] == 1
    # a.md and b.md should still have the stale entity (not processed).
    assert _load_entities(store / "notes" / "a.md")[0]["value"] == "Subject"
    assert _load_entities(store / "notes" / "b.md")[0]["value"] == "Subject"


def test_on_file_done_called_for_every_file(tmp_path):
    """on_file_done callback is called for every file, including those with no entities."""
    from convert import scrub

    store = make_store(tmp_path)
    make_md(store / "notes", "a.md", body="x", entities=[_entity("person", "Subject")])
    make_md(store / "notes", "b.md", body="x")  # no entities
    make_md(store / "notes", "c.md", body="x", entities=[_entity("org", "PayPal")])

    seen: list[str] = []
    scrub(store, {}, dry_run=True, on_file_done=seen.append)

    assert sorted(seen) == ["notes/a.md", "notes/b.md", "notes/c.md"]


def test_on_file_done_called_even_for_unchanged_files(tmp_path):
    """on_file_done is called even when no entities are removed from a file."""
    from convert import scrub

    store = make_store(tmp_path)
    make_md(store / "notes", "clean.md", body="x", entities=[_entity("org", "PayPal")])

    seen: list[str] = []
    scrub(store, {}, dry_run=True, on_file_done=seen.append)

    assert seen == ["notes/clean.md"]


def test_pilot_dump_incremental_flush(tmp_path):
    """Pilot records are written immediately — the file exists before the run ends."""
    import json
    from unittest.mock import patch

    from convert import scrub

    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Some context",
        entities=[_entity("person", "klicken Sie")],
    )

    dump_path = tmp_path / "pilot.jsonl"
    written_during_run: list[bool] = []

    original_flush = None

    def _fake_verify(value, type_, *, model, endpoint, api_key, context, cache):
        # Check whether the file has content at time of verify call.
        # After _write_pilot is called (flush), the file must have content.
        return "drop"

    with patch("zkm_ner.verifier.verify", side_effect=_fake_verify):
        scrub(
            store, {},
            dry_run=True,
            with_verifier=True,
            pilot_dump_path=dump_path,
        )

    # File must exist and have content after the run.
    assert dump_path.exists()
    records = [json.loads(l) for l in dump_path.read_text().splitlines() if l.strip()]
    assert len(records) >= 1
    assert records[0]["value"] == "klicken Sie"


def test_pilot_dump_appends_on_resume(tmp_path):
    """Pilot dump opened in append mode — existing records are not overwritten."""
    import json
    from unittest.mock import patch

    from convert import scrub

    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="context",
        entities=[_entity("person", "klicken Sie")],
    )

    dump_path = tmp_path / "pilot.jsonl"
    # Pre-seed the pilot file with a record from a previous partial run.
    dump_path.write_text(
        json.dumps({"value": "prior record", "type": "person", "verdict": "drop",
                    "suspicious_reason": "test", "file": "notes/prior.md",
                    "context_snippet": "", "is_control": False}) + "\n",
        encoding="utf-8",
    )

    def _fake_verify(value, type_, *, model, endpoint, api_key, context, cache):
        return "drop"

    with patch("zkm_ner.verifier.verify", side_effect=_fake_verify):
        scrub(
            store, {},
            dry_run=True,
            with_verifier=True,
            pilot_dump_path=dump_path,
        )

    records = [json.loads(l) for l in dump_path.read_text().splitlines() if l.strip()]
    assert len(records) == 2  # prior + new
    assert records[0]["value"] == "prior record"
    assert records[1]["value"] == "klicken Sie"
