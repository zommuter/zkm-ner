"""Tests for convert.py — zkm-ner amendment writer (N4)."""

from __future__ import annotations

import hashlib
from unittest.mock import patch, MagicMock

from tests.conftest import make_store, make_md


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entity(type_: str, value: str) -> dict:
    return {"type": type_, "value": value}


class _EntityStub:
    def __init__(self, type_: str, value: str) -> None:
        self.type = type_
        self.value = value

    def as_dict(self) -> dict:
        return {"type": self.type, "value": self.value}


def _body_sha256(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


# ---------------------------------------------------------------------------

def test_convert_emits_amendment_and_applies(tmp_path):
    """Happy path: md file → entities extracted → amendment applied to frontmatter."""
    store = make_store(tmp_path)
    md = make_md(store / "notes", "doc.md", body="Alice Smith visited Berlin.")

    entities_out = [_entity("person", "Alice Smith"), _entity("loc", "Berlin")]

    with (
        patch("zkm_ner.extract.extract", return_value=[
            _EntityStub("person", "Alice Smith"),
            _EntityStub("loc", "Berlin"),
        ]),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        result = convert(store, {})

    assert result == []

    import frontmatter
    post = frontmatter.load(md)
    assert post.metadata.get("entities") == entities_out


def test_convert_cache_hit_skips_extractor(tmp_path):
    """Cache hit must short-circuit the extractor call."""
    store = make_store(tmp_path)
    body = "Hello world."
    make_md(store / "notes", "doc.md", body=body)

    call_count = [0]

    def counting_extract(body, *, lang=None, gazetteer_path=None, model="spacy"):
        call_count[0] += 1
        return [_EntityStub("person", "Test")]

    from zkm.extraction_cache import ExtractionCache
    real_cache = ExtractionCache(store, extractor_name="ner")
    sha = _body_sha256(body)
    real_cache.put(sha, [_entity("person", "Test")], model_name="spacy", model_version="0.0.0")

    with (
        patch("zkm.extraction_cache.ExtractionCache", return_value=real_cache),
        patch("zkm_ner.extract.extract", side_effect=counting_extract),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})

    assert call_count[0] == 0, "Extractor must not be called on cache hit"


def test_convert_cache_miss_populates_cache(tmp_path):
    """Cache miss must call the extractor and write the result into the cache."""
    store = make_store(tmp_path)
    body = "Hello world."
    make_md(store / "notes", "doc.md", body=body)

    call_count = [0]

    def counting_extract(body, *, lang=None, gazetteer_path=None, model="spacy"):
        call_count[0] += 1
        return [_EntityStub("person", "Test")]

    from zkm.extraction_cache import ExtractionCache
    real_cache = ExtractionCache(store, extractor_name="ner")

    with (
        patch("zkm.extraction_cache.ExtractionCache", return_value=real_cache),
        patch("zkm_ner.extract.extract", side_effect=counting_extract),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})

    assert call_count[0] == 1

    sha = _body_sha256(body)
    cached = real_cache.get(sha, model_name="spacy", model_version="0.0.0")
    assert cached == [_entity("person", "Test")]


def test_convert_empty_entities_no_amendment(tmp_path):
    """Docs that yield zero entities must not emit any amendment record."""
    store = make_store(tmp_path)
    make_md(store / "notes", "empty.md", body="No entities here at all.")

    with (
        patch("zkm_ner.extract.extract", return_value=[]),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})

    queue_root = store / ".zkm-state/amendments"
    queue_files = list(queue_root.rglob("*.json")) if queue_root.exists() else []
    assert len(queue_files) == 0


def test_convert_idempotent_rerun(tmp_path):
    """Re-running convert on an already-enriched store must not duplicate entities."""
    store = make_store(tmp_path)
    md = make_md(store / "notes", "doc.md", body="Alice Smith visited Berlin.")

    with (
        patch("zkm_ner.extract.extract", return_value=[_EntityStub("person", "Alice Smith")]),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})  # first run
        convert(store, {})  # second run — cache hit + already-applied check

    import frontmatter
    post = frontmatter.load(md)
    ents = post.metadata.get("entities", [])
    alice = _entity("person", "Alice Smith")
    assert ents.count(alice) == 1, "Entity must not be duplicated on re-run"


def test_convert_body_sha256_stable_after_frontmatter_amendment(tmp_path):
    """Frontmatter-only changes (e.g. tags amended by notmuch) must not invalidate the cache."""
    store = make_store(tmp_path)
    md = make_md(store / "notes", "doc.md", body="Body content stays the same.")

    call_count = [0]

    def counting_extract(body, *, lang=None, gazetteer_path=None, model="spacy"):
        call_count[0] += 1
        return [_EntityStub("person", "Someone")]

    from zkm.extraction_cache import ExtractionCache
    real_cache = ExtractionCache(store, extractor_name="ner")

    with (
        patch("zkm.extraction_cache.ExtractionCache", return_value=real_cache),
        patch("zkm_ner.extract.extract", side_effect=counting_extract),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})  # first run — fills cache

    # Simulate a frontmatter-only amendment (e.g. notmuch adds tags)
    import frontmatter as fm
    post = fm.load(md)
    post.metadata["tags"] = ["amended"]
    md.write_text(fm.dumps(post), encoding="utf-8")

    with (
        patch("zkm.extraction_cache.ExtractionCache", return_value=real_cache),
        patch("zkm_ner.extract.extract", side_effect=counting_extract),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        convert(store, {})  # second run — must be cache hit

    assert call_count[0] == 1, "Extractor must not re-run after frontmatter-only change"
