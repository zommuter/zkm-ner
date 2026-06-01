"""spaCy NER backend for zkm-ner.

Uses de_core_news_sm + en_core_web_sm with doc-level langdetect routing.
Models are loaded once and cached in module-level dicts.
Mixed-language documents use doc-level detection — the limitation is accepted.
"""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache

import spacy
from langdetect import detect, LangDetectException

from zkm_ner._types import Entity

# spaCy label → zkm entity type
_LABEL_MAP = {
    # German model labels
    "PER": "person",
    "ORG": "org",
    "LOC": "loc",
    "MISC": "misc",
    # English model labels
    "PERSON": "person",
    "ORG": "org",
    "GPE": "loc",
    "LOC": "loc",
    "FAC": "loc",
    "NORP": "misc",
    "PRODUCT": "misc",
    "EVENT": "misc",
    "WORK_OF_ART": "misc",
    "LAW": "misc",
    "LANGUAGE": "misc",
}

# Temporal spaCy labels → γ type:datetime (handled separately with canonicalisation)
_TEMPORAL_LABELS = frozenset({"DATE", "TIME"})


@lru_cache(maxsize=4)
def _load_model(model_name: str):
    return spacy.load(model_name)


def _detect_lang(body: str) -> str:
    """Return two-letter ISO language code, defaulting to 'de' on failure."""
    try:
        return detect(body[:2000])  # first 2 kB is enough for doc-level detection
    except LangDetectException:
        return "de"


def extract_spacy(
    body: str,
    *,
    lang: str | None = None,
    doc_date: date | datetime | None = None,
) -> list[Entity]:
    """Run spaCy NER on *body* and return entity mentions.

    *lang* overrides doc-level langdetect when supplied.
    *doc_date* anchors relative date expressions (e.g. "Thursday") against the
    document's own frontmatter date when canonicalising γ type:datetime entities.
    """
    if not body.strip():
        return []

    effective_lang = lang or _detect_lang(body)
    model_name = "de_core_news_sm" if effective_lang.startswith("de") else "en_core_web_sm"

    nlp = _load_model(model_name)
    doc = nlp(body)

    results: list[Entity] = []
    for ent in doc.ents:
        if ent.label_ in _TEMPORAL_LABELS:
            _add_datetime_entity(ent.text, ent.start_char, ent.end_char, doc_date, effective_lang, results)
            continue
        etype = _LABEL_MAP.get(ent.label_)
        if etype is None:
            continue
        results.append(Entity(etype, ent.text, start=ent.start_char, end=ent.end_char, root_pos=ent.root.pos_))
    return results


def _add_datetime_entity(
    text: str,
    start: int,
    end: int,
    doc_date: date | datetime | None,
    lang: str,
    out: list[Entity],
) -> None:
    from zkm_ner.datetime_canon import canonicalise

    canonical = canonicalise(text, relative_base=doc_date, lang=lang)
    if canonical is None:
        return  # unparseable — skip rather than emit a low-quality entity

    value = text.strip()
    out.append(Entity(
        "datetime",
        value,
        # canonical must differ from value; both are strings but value is raw, canonical is ISO
        canonical=canonical if canonical != value else None,
        standard="ISO 8601",
        start=start,
        end=end,
        root_pos="",  # bypass POS filter — temporal label is deterministic
    ))
