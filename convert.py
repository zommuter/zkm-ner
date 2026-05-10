"""zkm-ner — amend md frontmatter with NER entity mentions.

Loads each md file in the store, runs entity extraction (pattern overlay +
spaCy NER or GLiNER) with an extraction-cache short-circuit, then emits
amendment records via zkm.amendments for the `entities` field.

Returns [] — amender pattern; body output is not produced here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_plugin_root = Path(__file__).parent
sys.path.insert(0, str(_plugin_root / "src"))
_venv_site = list((_plugin_root / ".venv").glob("lib/python*/site-packages"))
if _venv_site:
    sys.path.insert(0, str(_venv_site[0]))

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

    from zkm_ner.version import model_version

    cache = ExtractionCache(store_path, extractor_name=PLUGIN_NAME)
    version = model_version(model_name)

    md_files = sorted(store_path.rglob("*.md"))
    total = len(md_files)

    for i, md_path in enumerate(md_files, 1):
        _process_file(
            md_path,
            store_path=store_path,
            cache=cache,
            extract=extract,
            model_name=model_name,
            model_version=version,
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
    model_version: str,
    forced_lang: str | None,
    gazetteer_path: str | None,
) -> None:
    import hashlib
    import frontmatter

    try:
        post = frontmatter.load(str(md_path))
    except Exception:
        return

    body = post.content
    body_sha256 = hashlib.sha256(body.encode()).hexdigest()

    cached = cache.get(body_sha256, model_name=model_name, model_version=model_version)
    if cached is not None:
        entities = cached
    else:
        lang = forced_lang or post.get("lang") or None
        entities = [e.as_dict() for e in extract(body, lang=lang, gazetteer_path=gazetteer_path, model=model_name)]
        cache.put(body_sha256, entities, model_name=model_name, model_version=model_version)

    if not entities:
        return

    emit(
        store_path,
        key={"path": str(md_path.relative_to(store_path))},
        fields={"entities": entities},
        emitted_by=PLUGIN_NAME,
    )


# ---------------------------------------------------------------------------


def scrub(
    store_path: Path,
    config: dict,  # noqa: ARG001
    *,
    dry_run: bool = True,
    verbose: bool = False,
    progress=None,
) -> dict[str, int]:
    """Remove stoplist entities from existing frontmatter (retroactive cleanup).

    Does NOT touch amendment attribution sidecars (<md>.amendments.json).
    Idempotent: second run with dry_run=False reports files_changed=0.
    """
    import frontmatter

    from zkm.atomic import write_atomic
    from zkm_ner.textfilter import _STOPLIST

    md_files = [
        p for p in sorted(store_path.rglob("*.md"))
        if not any(part.startswith(".") for part in p.relative_to(store_path).parts[:-1])
    ]
    total = len(md_files)
    files_changed = 0
    entities_removed = 0

    for i, md_path in enumerate(md_files, 1):
        if progress:
            progress(i, total, str(md_path.relative_to(store_path)))
        try:
            post = frontmatter.load(str(md_path))
        except Exception:
            continue

        existing = post.metadata.get("entities")
        if not existing:
            continue

        cleaned = [
            e for e in existing
            if not (isinstance(e, dict) and e.get("value", "").strip().lower() in _STOPLIST)
        ]
        removed = len(existing) - len(cleaned)
        if removed == 0:
            continue

        entities_removed += removed
        files_changed += 1
        if verbose:
            print(f"  {md_path.relative_to(store_path)}  (-{removed} entities)", file=sys.stderr)

        if not dry_run:
            post.metadata["entities"] = cleaned
            write_atomic(md_path, frontmatter.dumps(post))

    return {"files_scanned": total, "files_changed": files_changed, "entities_removed": entities_removed}
