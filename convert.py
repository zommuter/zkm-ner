"""zkm-ner — amend md frontmatter with NER entity mentions.

Loads each md file in the store, runs entity extraction (pattern overlay +
spaCy NER or GLiNER) with an extraction-cache short-circuit, then emits
amendment records via zkm.amendments for the `entities` field.

Returns [] — amender pattern; body output is not produced here.
"""

from __future__ import annotations

import sys
from pathlib import Path

from zkm.amendments import apply_queue, emit

PLUGIN_NAME = "ner"
PLUGIN_VERSION = "0.1.0"


def convert(store_path: Path, config: dict, *, progress=None) -> list[Path]:
    """Amend all md files in *store_path* with NER entity mentions.

    Returns [] — amender pattern.
    """
    from zkm_ner.extract import extract
    from zkm.extraction_cache import ExtractionCache

    model_name = config.get("ZKM_NER_MODEL", "spacy").strip() or "spacy"
    forced_lang = config.get("ZKM_NER_LANG", "").strip() or None
    gazetteer_path = config.get("ZKM_NER_GAZETTEER", "").strip() or None

    cache = ExtractionCache(store_path, extractor_name=PLUGIN_NAME)

    md_files = sorted(store_path.rglob("*.md"))
    total = len(md_files)

    for i, md_path in enumerate(md_files, 1):
        _process_file(
            md_path,
            store_path=store_path,
            cache=cache,
            extract=extract,
            model_name=model_name,
            forced_lang=forced_lang,
            gazetteer_path=gazetteer_path,
        )
        if progress:
            progress(i, total, str(md_path.relative_to(store_path)))

    applied, pending = apply_queue(store_path)
    if applied:
        print(f"zkm-ner: applied {applied} amendment(s)", file=sys.stderr)
    if pending:
        print(f"zkm-ner: {pending} amendment(s) pending", file=sys.stderr)

    return []


# ---------------------------------------------------------------------------


def _process_file(
    md_path: Path,
    *,
    store_path: Path,
    cache,
    extract,
    model_name: str,
    forced_lang: str | None,
    gazetteer_path: str | None,
) -> None:
    import frontmatter
    from zkm.hashing import sha256_file

    try:
        post = frontmatter.load(str(md_path))
    except Exception:
        return

    body = post.content
    body_sha256 = sha256_file(md_path)

    cached = cache.get(body_sha256, model_name=model_name)
    if cached is not None:
        entities = cached
    else:
        lang = forced_lang or post.get("lang") or None
        entities = [e.as_dict() for e in extract(body, lang=lang, gazetteer_path=gazetteer_path, model=model_name)]
        cache.put(body_sha256, entities, model_name=model_name)

    if not entities:
        return

    emit(
        store_path,
        key={"path": str(md_path.relative_to(store_path))},
        fields={"entities": entities},
        emitted_by=PLUGIN_NAME,
    )
