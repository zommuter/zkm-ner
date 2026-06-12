"""Spec tests for roadmap:2b76 — convert's full sweep must skip hidden dirs.

``scrub()`` already filters out paths with a dot-prefixed directory component;
``convert()`` with ``created=None`` does not, so md files under ``.zkm-state/``
or ``.git/`` get extracted and amended. Parity fix using the same predicate.
An explicit ``created=[…]`` list stays unfiltered (caller's responsibility).
See ROADMAP.md id:2b76.
"""

from __future__ import annotations

from unittest.mock import patch

from tests.conftest import make_store, make_md


def _recording_extract(processed: list):
    def fake_extract(body, *, lang=None, gazetteer_path=None, model="spacy", doc_date=None):
        processed.append(body)
        return []
    return fake_extract


def test_full_sweep_skips_dot_directories(tmp_path):  # roadmap:2b76
    """md files under dot-prefixed directories are not processed."""
    store = make_store(tmp_path)
    make_md(store / "notes", "visible.md", body="Visible note body.")
    make_md(store / ".zkm-state", "hidden-state.md", body="Hidden state body.")
    make_md(store / ".git" / "info", "hidden-git.md", body="Hidden git body.")

    processed: list = []
    with (
        patch("zkm_ner.extract.extract", side_effect=_recording_extract(processed)),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})

    assert processed == ["Visible note body."]


def test_full_sweep_still_processes_visible_files(tmp_path):  # roadmap:2b76
    """All visible files (nested included) are swept; only hidden ones are skipped."""
    store = make_store(tmp_path)
    make_md(store / "notes", "a.md", body="Alpha body.")
    make_md(store / "notes" / "sub", "b.md", body="Beta body.")
    make_md(store / ".zkm-state", "c.md", body="Hidden body.")

    processed: list = []
    with (
        patch("zkm_ner.extract.extract", side_effect=_recording_extract(processed)),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})

    assert sorted(processed) == ["Alpha body.", "Beta body."]


def test_created_list_not_filtered(tmp_path):  # roadmap:2b76
    """GUARD (green pre-implementation): an explicit created= list is honoured
    verbatim — the hidden-dir filter applies to the full sweep only. Protects
    against over-filtering when implementing the sweep predicate.
    """
    store = make_store(tmp_path)
    hidden = make_md(store / ".zkm-state", "explicit.md", body="Explicitly requested body.")

    processed: list = []
    with (
        patch("zkm_ner.extract.extract", side_effect=_recording_extract(processed)),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {}, created=[hidden])

    assert processed == ["Explicitly requested body."]
