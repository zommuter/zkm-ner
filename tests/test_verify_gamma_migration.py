"""Tests for scripts/verify_gamma_migration.py (E5)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from tests.conftest import make_store, make_md

# Load the script as a module (it lives in scripts/, not a package).
_SCRIPT = Path(__file__).parent.parent / "scripts" / "verify_gamma_migration.py"
_spec = importlib.util.spec_from_file_location("verify_gamma_migration", _SCRIPT)
assert _spec and _spec.loader
_vgm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vgm)  # type: ignore[union-attr]

_ent_scope = _vgm._ent_scope
_ent_key = _vgm._ent_key
verify = _vgm.verify


# ---------------------------------------------------------------------------
# Unit tests for graceful-read helpers
# ---------------------------------------------------------------------------


def test_ent_scope_pre_gamma_defaults_to_body():
    assert _ent_scope({"type": "person", "value": "Alice"}) == "body"


def test_ent_scope_gamma_entry_signature():
    assert _ent_scope({"scope": "signature", "type": "email_address", "value": "a@b.com"}) == "signature"


def test_ent_scope_gamma_entry_body():
    assert _ent_scope({"scope": "body", "type": "org", "value": "SBB"}) == "body"


def test_ent_key_pre_gamma():
    assert _ent_key({"type": "person", "value": "Alice"}) == ("body", "person", "Alice")


def test_ent_key_gamma_signature():
    assert _ent_key({"scope": "signature", "type": "email_address", "value": "a@b.com"}) == (
        "signature", "email_address", "a@b.com"
    )


def test_ent_key_pre_gamma_equals_explicit_body():
    pre = {"type": "org", "value": "PayPal"}
    gamma = {"scope": "body", "type": "org", "value": "PayPal"}
    assert _ent_key(pre) == _ent_key(gamma)


# ---------------------------------------------------------------------------
# verify() integration tests (extract mocked)
# ---------------------------------------------------------------------------


def _fresh(type_: str, value: str, scope: str = "body") -> dict:
    return {"scope": scope, "type": type_, "value": value}


def test_verify_exact_agreement(tmp_path):
    """Stored entities == fresh extraction → agreement=1, no gate failures."""
    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Alice visited Berlin.",
        entities=[
            {"scope": "body", "type": "person", "value": "Alice"},
            {"scope": "body", "type": "loc", "value": "Berlin"},
        ],
    )
    fresh = [_fresh("person", "Alice"), _fresh("loc", "Berlin")]
    with patch.object(_vgm, "_extract_fresh", return_value=fresh):
        stats = verify(store, sample_size=10, seed=0, full_corpus=True,
                       out_path=tmp_path / "diff.jsonl")

    assert stats["n"] == 1
    assert stats["agreement"] == 1
    assert stats["agreement_rate"] == 1.0
    assert stats["collision_files"] == 0
    assert stats["schema_error_files"] == 0


def test_verify_pre_gamma_entry_agrees_with_fresh_body_scope(tmp_path):
    """Pre-γ entry (no scope) == fresh body-scope entry via graceful-read → no collision."""
    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Bob in Zurich.",
        entities=[{"type": "person", "value": "Bob"}],  # pre-γ, no scope
    )
    with patch.object(_vgm, "_extract_fresh", return_value=[_fresh("person", "Bob")]):
        stats = verify(store, sample_size=10, seed=0, full_corpus=True,
                       out_path=tmp_path / "diff.jsonl")

    assert stats["pre_gamma_files"] == 1
    assert stats["pre_gamma_entities"] == 1
    assert stats["collision_files"] == 0
    assert stats["agreement"] == 1


def test_verify_collision_pre_gamma_plus_explicit_body(tmp_path):
    """Same (body, type, value) twice (pre-γ + explicit γ) → collision_files=1 → gate fails."""
    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Carol Carol.",
        entities=[
            {"type": "person", "value": "Carol"},              # pre-γ → scope=body
            {"scope": "body", "type": "person", "value": "Carol"},  # explicit body
        ],
    )
    with patch.object(_vgm, "_extract_fresh", return_value=[]):
        stats = verify(store, sample_size=10, seed=0, full_corpus=True,
                       out_path=tmp_path / "diff.jsonl")

    assert stats["collision_files"] == 1


def test_verify_different_scopes_no_collision(tmp_path):
    """Same (type, value) under different scopes → NOT a collision."""
    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Dave dave@example.com",
        entities=[
            {"scope": "body", "type": "email_address", "value": "dave@example.com"},
            {"scope": "signature", "type": "email_address", "value": "dave@example.com"},
        ],
    )
    with patch.object(_vgm, "_extract_fresh", return_value=[]):
        stats = verify(store, sample_size=10, seed=0, full_corpus=True,
                       out_path=tmp_path / "diff.jsonl")

    assert stats["collision_files"] == 0


def test_verify_schema_error_entity_missing_value(tmp_path):
    """Entity missing 'value' → schema_error_files=1 → gate fails."""
    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Eve here.",
        entities=[{"type": "person"}],  # missing value
    )
    with patch.object(_vgm, "_extract_fresh", return_value=[]):
        stats = verify(store, sample_size=10, seed=0, full_corpus=True,
                       out_path=tmp_path / "diff.jsonl")

    assert stats["schema_error_files"] == 1


def test_verify_pipeline_drift_is_informational(tmp_path):
    """Stored != fresh (pipeline drift) → agreement=0 but no gate failure."""
    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Frank at OldCorp.",
        entities=[
            {"scope": "body", "type": "person", "value": "Frank"},
            {"scope": "body", "type": "org", "value": "OldCorp"},
        ],
    )
    # Pipeline no longer emits OldCorp (cleaned up by scrub / model improvement)
    with patch.object(_vgm, "_extract_fresh", return_value=[_fresh("person", "Frank")]):
        stats = verify(store, sample_size=10, seed=0, full_corpus=True,
                       out_path=tmp_path / "diff.jsonl")

    assert stats["collision_files"] == 0
    assert stats["schema_error_files"] == 0
    assert stats["agreement"] == 0
    assert stats["only_in_stored"] == 1
    assert stats["only_in_fresh"] == 0


def test_verify_diff_jsonl_written_for_non_agreeing_files(tmp_path):
    """Non-agreeing files get a diff record in the JSONL output."""
    store = make_store(tmp_path)
    make_md(
        store / "notes", "doc.md",
        body="Grace at NewCorp.",
        entities=[{"scope": "body", "type": "person", "value": "Grace"}],
    )
    out = tmp_path / "diff.jsonl"
    with patch.object(_vgm, "_extract_fresh", return_value=[]):
        verify(store, sample_size=10, seed=0, full_corpus=True, out_path=out)

    assert out.exists()
    records = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(records) == 1
    rec = records[0]
    assert rec["file"] == "notes/doc.md"
    assert rec["stored"] == 1
    assert rec["fresh"] == 0
    assert ["body", "person", "Grace"] in rec["only_in_stored"]


def test_verify_no_entities_file_skipped(tmp_path):
    """Files without entities are not sampled."""
    store = make_store(tmp_path)
    make_md(store / "notes", "empty.md", body="No entities here.")
    with patch.object(_vgm, "_extract_fresh", return_value=[]):
        stats = verify(store, sample_size=10, seed=0, full_corpus=True,
                       out_path=tmp_path / "diff.jsonl")

    assert stats["n"] == 0
