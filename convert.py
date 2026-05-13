"""zkm-ner — amend md frontmatter with NER entity mentions.

Loads each md file in the store, runs entity extraction (pattern overlay +
spaCy NER or GLiNER) with an extraction-cache short-circuit, then emits
amendment records via zkm.amendments for the `entities` field.

Returns [] — amender pattern; body output is not produced here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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
    sig_block: str = post.get("signature_block") or ""
    sal_block: str = post.get("salutation_block") or ""

    # Cache key covers all text sections so scope-tagged entities are invalidated
    # when signature_block / salutation_block change after a re-render.
    combined = body + "\x00" + sig_block + "\x00" + sal_block
    combined_sha256 = hashlib.sha256(combined.encode()).hexdigest()

    cached = cache.get(combined_sha256, model_name=model_name, model_version=model_version)
    if cached is not None:
        entities = cached
    else:
        lang = forced_lang or post.get("lang") or None
        kwargs = dict(lang=lang, gazetteer_path=gazetteer_path, model=model_name)

        body_entities = [e.as_dict() for e in extract(body, **kwargs)]

        sig_entities: list = []
        if sig_block:
            for e in extract(sig_block, **kwargs):
                e.scope = "signature"
                sig_entities.append(e.as_dict())

        sal_entities: list = []
        if sal_block:
            for e in extract(sal_block, **kwargs):
                e.scope = "salutation"
                sal_entities.append(e.as_dict())

        entities = body_entities + sig_entities + sal_entities
        cache.put(combined_sha256, entities, model_name=model_name, model_version=model_version)

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
    config: dict,
    *,
    dry_run: bool = True,
    verbose: bool = False,
    progress=None,
    with_verifier: bool = False,
    with_verifier_control_pct: float = 0.0,
    pilot_dump_path: "Path | None" = None,
    resume_after_file: "str | None" = None,
    on_file_done: "object | None" = None,
    **_ignored,
) -> dict[str, int]:
    """Remove stoplist entities from existing frontmatter (retroactive cleanup).

    Does NOT touch amendment attribution sidecars (<md>.amendments.json).
    Idempotent: second run with dry_run=False reports files_changed=0.

    When *with_verifier* is True, entities flagged as suspicious that survive the
    heuristic checks are additionally sent to an LLM verifier; those returning
    "drop" are included in the removal set.  Verifier config is read from *config*
    (``ZKM_NER_VERIFIER_MODEL``, ``ZKM_NER_VERIFIER_ENDPOINT``,
    ``ZKM_NER_VERIFIER_KEY``; fall back to the main LLM config keys).

    When *with_verifier_control_pct* > 0 a random sample of non-suspicious
    entities at that percentage is also run through the verifier as a blind-spot
    tripwire; any non-"keep" verdict is logged to stderr.
    """
    import json
    import random

    import frontmatter

    from zkm.atomic import write_atomic
    from zkm_ner.textfilter import _COMMONNOUN_STOPLIST, _RE_SECTION_LINK_ARTIFACT, _RE_STRUCTURAL_ARTEFACT, _SALUTATION_BLOCKLIST, _STOPLIST

    md_files = [
        p for p in sorted(store_path.rglob("*.md"))
        if not any(part.startswith(".") for part in p.relative_to(store_path).parts[:-1])
    ]

    # Skip files already processed in an interrupted run.
    if resume_after_file is not None:
        resume_rel = Path(resume_after_file)
        resume_idx = next(
            (j for j, p in enumerate(md_files) if p.relative_to(store_path) == resume_rel),
            None,
        )
        if resume_idx is not None:
            md_files = md_files[resume_idx + 1:]

    total = len(md_files)
    files_changed = 0
    entities_removed = 0
    entities_dropped_by_verifier = 0
    control_sampled = 0
    control_alerts = 0
    _pilot_count = 0  # records written to pilot_dump_path

    # Lazy-loaded spaCy models for isolated POS check; None = not tried, False = unavailable.
    _nlp_de: Any = None
    _nlp_en: Any = None
    _pos_cache: dict[str, str] = {}
    _KEEP_POS = frozenset({"PROPN", "X"})

    def _isolated_pos(value: str) -> str:
        """Return spaCy POS of first token when *value* is analysed in isolation.

        Checks DE model first; if DE says PROPN/X, retries with EN to catch
        English common words (e.g. 'Learn' VERB, 'Link' NOUN) that the German
        model incorrectly treats as proper nouns.  Returns "" on failure.
        Single-word values only — multi-word entities bypass this check.
        """
        nonlocal _nlp_de, _nlp_en
        if " " in value:
            return ""
        if value in _pos_cache:
            return _pos_cache[value]

        if _nlp_de is None:
            try:
                import spacy
                _nlp_de = spacy.load("de_core_news_sm")
            except Exception:
                _nlp_de = False

        pos_de = ""
        if _nlp_de is not False:
            try:
                doc = _nlp_de(value)  # type: ignore[operator]
                pos_de = doc[0].pos_ if doc else ""
            except Exception:
                pass

        if pos_de and pos_de not in _KEEP_POS:
            _pos_cache[value] = pos_de
            return pos_de

        if _nlp_en is None:
            try:
                import spacy
                _nlp_en = spacy.load("en_core_web_sm")
            except Exception:
                _nlp_en = False

        pos_en = ""
        if _nlp_en is not False:
            try:
                doc = _nlp_en(value)  # type: ignore[operator]
                pos_en = doc[0].pos_ if doc else ""
            except Exception:
                pass

        if pos_en and pos_en not in _KEEP_POS:
            _pos_cache[value] = pos_en
            return pos_en

        pos = pos_de or pos_en
        _pos_cache[value] = pos
        return pos

    # ------------------------------------------------------------------
    # Verifier setup (lazy — only when with_verifier is True)
    # ------------------------------------------------------------------
    _verifier_run = None
    _is_suspicious_fn = None
    _verifier_cache = None

    if with_verifier:
        from zkm.extraction_cache import ExtractionCache
        from zkm_ner.suspicious import is_suspicious as _is_suspicious_fn  # type: ignore[assignment]
        from zkm_ner.verifier import verify as _verify_fn

        _v_model = (
            config.get("ZKM_NER_VERIFIER_MODEL")
            or config.get("ZKM_LLM_MODEL", "")
            or "aya-expanse-8b"
        )
        _v_endpoint = (
            config.get("ZKM_NER_VERIFIER_ENDPOINT")
            or config.get("ZKM_LLM_ENDPOINT", "")
            or "http://localhost:8080"
        )
        _v_key = config.get("ZKM_NER_VERIFIER_KEY") or config.get("ZKM_LLM_API_KEY", "")
        _verifier_cache = ExtractionCache(store_path, extractor_name="ner_verifier")

        def _verifier_run(e: Any, context: str | None) -> str:
            return _verify_fn(
                e["value"], e["type"],
                model=_v_model,
                endpoint=_v_endpoint,
                api_key=_v_key,
                context=context,
                cache=_verifier_cache,
            )

    def _is_heuristic_candidate(e: Any) -> bool:
        """Return True if heuristic rules flag *e* for removal."""
        if not isinstance(e, dict):
            return False
        value = e.get("value", "")
        value_lower = value.strip().lower()
        if value_lower in _STOPLIST or value_lower in _COMMONNOUN_STOPLIST or value_lower in _SALUTATION_BLOCKLIST:
            return True
        if _RE_STRUCTURAL_ARTEFACT.match(value):
            return True
        if _RE_SECTION_LINK_ARTIFACT.match(value):
            return True
        pos = _isolated_pos(value.strip())
        return bool(pos) and pos not in {"PROPN", "X"}

    # Open pilot dump file in append mode for incremental flushing.
    _pilot_fh = None
    if pilot_dump_path is not None:
        pilot_dump_path.parent.mkdir(parents=True, exist_ok=True)
        _pilot_fh = open(pilot_dump_path, "a", encoding="utf-8")  # noqa: SIM115

    def _write_pilot(record: dict) -> None:
        nonlocal _pilot_count
        if _pilot_fh is not None:
            _pilot_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            _pilot_fh.flush()
            _pilot_count += 1

    try:
        for i, md_path in enumerate(md_files, 1):
            if progress:
                progress(i, total, str(md_path.relative_to(store_path)))

            _rel = str(md_path.relative_to(store_path))

            def _mark_done() -> None:
                if on_file_done is not None:
                    on_file_done(_rel)  # type: ignore[operator]

            try:
                post = frontmatter.load(str(md_path))
            except Exception:
                _mark_done()
                continue

            existing = post.metadata.get("entities")
            if not existing:
                _mark_done()
                continue

            body_context: str | None = post.content[:800] if with_verifier else None

            cleaned: list = []
            file_verifier_drops = 0
            for e in existing:
                if _is_heuristic_candidate(e):
                    continue  # heuristic removal
                if (
                    with_verifier
                    and _verifier_run is not None
                    and _is_suspicious_fn is not None
                    and isinstance(e, dict)
                    and _is_suspicious_fn(e.get("type", ""), e.get("value", ""))
                ):
                    verdict = _verifier_run(e, body_context)
                    _write_pilot({
                        "value": e.get("value"), "type": e.get("type"),
                        "verdict": verdict,
                        "suspicious_reason": _is_suspicious_fn(e.get("type", ""), e.get("value", "")),
                        "file": _rel,
                        "context_snippet": (body_context or "")[:200],
                        "is_control": False,
                    })
                    if verdict == "drop":
                        file_verifier_drops += 1
                        continue  # verifier removal
                cleaned.append(e)

            removed = len(existing) - len(cleaned)
            entities_dropped_by_verifier += file_verifier_drops

            if removed == 0:
                # Control-sample pass even when nothing was removed
                if (
                    with_verifier
                    and with_verifier_control_pct > 0
                    and _verifier_run is not None
                    and _is_suspicious_fn is not None
                ):
                    for e in cleaned:
                        if not isinstance(e, dict):
                            continue
                        if _is_suspicious_fn(e.get("type", ""), e.get("value", "")):
                            continue  # skip suspicious — they were already checked above
                        if random.random() < with_verifier_control_pct / 100.0:
                            verdict = _verifier_run(e, body_context)
                            control_sampled += 1
                            _write_pilot({
                                "value": e.get("value"), "type": e.get("type"),
                                "verdict": verdict,
                                "suspicious_reason": None,
                                "file": _rel,
                                "context_snippet": (body_context or "")[:200],
                                "is_control": True,
                            })
                            if verdict != "keep":
                                control_alerts += 1
                                print(
                                    f"zkm-ner: CONTROL-SAMPLE ALERT: "
                                    f"{e.get('type')}={e.get('value')!r} → {verdict}",
                                    file=sys.stderr,
                                )
                _mark_done()
                continue

            entities_removed += removed
            files_changed += 1
            if verbose:
                print(f"  {md_path.relative_to(store_path)}  (-{removed} entities)", file=sys.stderr)

            # Control-sample on the retained entities of changed files
            if (
                with_verifier
                and with_verifier_control_pct > 0
                and _verifier_run is not None
                and _is_suspicious_fn is not None
            ):
                for e in cleaned:
                    if not isinstance(e, dict):
                        continue
                    if _is_suspicious_fn(e.get("type", ""), e.get("value", "")):
                        continue
                    if random.random() < with_verifier_control_pct / 100.0:
                        verdict = _verifier_run(e, body_context)
                        control_sampled += 1
                        _write_pilot({
                            "value": e.get("value"), "type": e.get("type"),
                            "verdict": verdict,
                            "suspicious_reason": None,
                            "file": _rel,
                            "context_snippet": (body_context or "")[:200],
                            "is_control": True,
                        })
                        if verdict != "keep":
                            control_alerts += 1
                            print(
                                f"zkm-ner: CONTROL-SAMPLE ALERT: "
                                f"{e.get('type')}={e.get('value')!r} → {verdict}",
                                file=sys.stderr,
                            )

            if not dry_run:
                post.metadata["entities"] = cleaned
                write_atomic(md_path, frontmatter.dumps(post))

            _mark_done()

    finally:
        if _pilot_fh is not None:
            _pilot_fh.close()

    return {
        "files_scanned": total,
        "files_changed": files_changed,
        "entities_removed": entities_removed,
        "entities_dropped_by_verifier": entities_dropped_by_verifier,
        "control_sampled": control_sampled,
        "control_alerts": control_alerts,
        "pilot_records": _pilot_count,
    }
