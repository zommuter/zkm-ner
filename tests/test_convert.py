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


def _combined_sha256(body: str, sig: str = "", sal: str = "") -> str:
    """Matches the cache key formula in _process_file."""
    combined = body + "\x00" + sig + "\x00" + sal
    return hashlib.sha256(combined.encode()).hexdigest()


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
    real_cache.put(_combined_sha256(body), [_entity("person", "Test")], model_name="spacy", model_version="0.0.0")

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

    cached = real_cache.get(_combined_sha256(body), model_name="spacy", model_version="0.0.0")
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


# ---------------------------------------------------------------------------
# Signature / salutation scope extraction (N9g-pre / E12)
# ---------------------------------------------------------------------------

class _EntityObj:
    """Minimal real-Entity-like object with mutable scope for scope-overide tests."""
    def __init__(self, type_: str, value: str, scope: str = "body") -> None:
        self.type = type_
        self.value = value
        self.scope = scope
        self.canonical = None
        self.standard = None
        self.unit = None
        self.valid = True

    def as_dict(self) -> dict:
        d: dict = {"scope": self.scope, "type": self.type, "value": self.value}
        return d


def test_signature_block_entities_get_signature_scope(tmp_path):
    """Entities extracted from signature_block frontmatter field must carry scope='signature'."""
    store = make_store(tmp_path)
    body = "Please find the invoice attached."
    sig = "Best regards\nAlice Smith\nalice@example.com"
    make_md(store / "mail", "msg.md", body=body, signature_block=sig)

    calls: list[str] = []

    def scoped_extract(text, *, lang=None, gazetteer_path=None, model="spacy"):
        calls.append(text)
        if "alice@example.com" in text:
            return [_EntityObj("email_address", "alice@example.com")]
        return [_EntityObj("person", "Someone")]

    with (
        patch("zkm_ner.extract.extract", side_effect=scoped_extract),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})

    import frontmatter
    post = frontmatter.load(str(store / "mail" / "msg.md"))
    entities = post.metadata.get("entities", [])
    sig_ents = [e for e in entities if e.get("scope") == "signature"]
    assert any(e["value"] == "alice@example.com" for e in sig_ents), (
        "email from signature_block must have scope='signature'"
    )


def test_salutation_block_entities_get_salutation_scope(tmp_path):
    """Entities extracted from salutation_block frontmatter field must carry scope='salutation'."""
    store = make_store(tmp_path)
    body = "Your order has been shipped."
    sal = "Dear John Doe,"
    make_md(store / "mail", "msg.md", body=body, salutation_block=sal)

    def scoped_extract(text, *, lang=None, gazetteer_path=None, model="spacy"):
        if "John Doe" in text:
            return [_EntityObj("person", "John Doe")]
        return []

    with (
        patch("zkm_ner.extract.extract", side_effect=scoped_extract),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})

    import frontmatter
    post = frontmatter.load(str(store / "mail" / "msg.md"))
    entities = post.metadata.get("entities", [])
    sal_ents = [e for e in entities if e.get("scope") == "salutation"]
    assert any(e["value"] == "John Doe" for e in sal_ents), (
        "person from salutation_block must have scope='salutation'"
    )


def test_body_entities_default_scope_unaffected(tmp_path):
    """Body-text entities must still use whatever scope the extractor returns (default 'body')."""
    store = make_store(tmp_path)
    make_md(store / "notes", "doc.md", body="Bob visited Zurich.")

    with (
        patch("zkm_ner.extract.extract", return_value=[
            _EntityObj("person", "Bob"),
            _EntityObj("loc", "Zurich"),
        ]),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})

    import frontmatter
    post = frontmatter.load(str(store / "notes" / "doc.md"))
    entities = post.metadata.get("entities", [])
    assert all(e.get("scope") == "body" for e in entities), (
        "plain body entities must carry scope='body'"
    )


def test_cache_key_includes_signature_block(tmp_path):
    """Adding a signature_block to a file must cause a cache miss (new combined key)."""
    store = make_store(tmp_path)
    body = "Hello world."
    md = make_md(store / "notes", "doc.md", body=body)

    call_count = [0]

    def counting_extract(text, *, lang=None, gazetteer_path=None, model="spacy"):
        call_count[0] += 1
        return []

    from zkm.extraction_cache import ExtractionCache
    real_cache = ExtractionCache(store, extractor_name="ner")
    # Pre-populate with body-only key (no sig/sal)
    real_cache.put(_combined_sha256(body), [], model_name="spacy", model_version="0.0.0")

    # Now add a signature_block to the md file
    import frontmatter as fm
    post = fm.load(str(md))
    post.metadata["signature_block"] = "Best regards\nAlice"
    md.write_text(fm.dumps(post), encoding="utf-8")

    with (
        patch("zkm.extraction_cache.ExtractionCache", return_value=real_cache),
        patch("zkm_ner.extract.extract", side_effect=counting_extract),
        patch("zkm_ner.version.model_version", return_value="0.0.0"),
    ):
        from convert import convert
        convert(store, {})

    assert call_count[0] > 0, "Adding signature_block must bust the cache"
