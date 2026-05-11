"""spaCy NER backend for zkm-ner.

Uses de_core_news_sm + en_core_web_sm with doc-level langdetect routing.
Models are loaded once and cached in module-level dicts.
Mixed-language documents use doc-level detection — the limitation is accepted.
"""

from __future__ import annotations

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


@lru_cache(maxsize=4)
def _load_model(model_name: str):
    return spacy.load(model_name)


def _detect_lang(body: str) -> str:
    """Return two-letter ISO language code, defaulting to 'de' on failure."""
    try:
        return detect(body[:2000])  # first 2 kB is enough for doc-level detection
    except LangDetectException:
        return "de"


def extract_spacy(body: str, *, lang: str | None = None) -> list[Entity]:
    """Run spaCy NER on *body* and return entity mentions.

    *lang* overrides doc-level langdetect when supplied.
    """
    if not body.strip():
        return []

    effective_lang = lang or _detect_lang(body)
    model_name = "de_core_news_sm" if effective_lang.startswith("de") else "en_core_web_sm"

    nlp = _load_model(model_name)
    doc = nlp(body)

    results: list[Entity] = []
    for ent in doc.ents:
        etype = _LABEL_MAP.get(ent.label_)
        if etype is None:
            continue
        results.append(Entity(etype, ent.text, start=ent.start_char, end=ent.end_char, root_pos=ent.root.pos_))
    return results
