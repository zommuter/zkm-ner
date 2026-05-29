"""Entity extractor — pattern overlay + spaCy NER (+ optional GLiNER).

Public API:
    extract(body, *, lang, model, gazetteer_path) -> list[Entity]

Entity is re-exported for callers that only import from this module.
"""

from __future__ import annotations

from zkm_ner._types import Entity  # re-export
from zkm_ner.patterns import extract_all as _extract_patterns
from zkm_ner.spacy_backend import extract_spacy
from zkm_ner.textfilter import drop_commonnoun_stoplist, drop_html_entity_artefacts, drop_salutation_blocklist, drop_section_link_artefacts, drop_stoplist, drop_structural_artefacts, strip_markdown_artefacts

__all__ = ["Entity", "extract"]


def extract(
    body: str,
    *,
    lang: str | None = None,
    model: str = "spacy",
    gazetteer_path: str | None = None,
) -> list[Entity]:
    """Return deduplicated entity mentions extracted from *body*.

    Pattern overlay runs first; any NER span that overlaps a pattern span is
    dropped (patterns win).  Final list is deduped on (type, value).
    """
    body = strip_markdown_artefacts(body)
    pattern_ents = _extract_patterns(body, gazetteer_path=gazetteer_path)

    if model == "gliner":
        from zkm_ner.gliner_backend import extract_gliner
        ner_ents = extract_gliner(body, lang=lang)
    else:
        ner_ents = extract_spacy(body, lang=lang)

    pattern_spans = [(e.start, e.end) for e in pattern_ents if e.start >= 0]
    merged = list(pattern_ents)
    for ner_ent in ner_ents:
        if not _pos_filter(ner_ent):
            continue
        if ner_ent.start >= 0 and _overlaps_any(ner_ent.start, ner_ent.end, pattern_spans):
            continue
        merged.append(ner_ent)

    return _dedup(drop_html_entity_artefacts(drop_section_link_artefacts(drop_salutation_blocklist(drop_structural_artefacts(drop_commonnoun_stoplist(drop_stoplist(merged)))))))


# ---------------------------------------------------------------------------

def _pos_filter(entity: Entity) -> bool:
    """Return True if entity should pass the POS gate.

    spaCy NER entities are kept only when the root token is PROPN.
    Pattern-overlay entities have root_pos="" (no NLP context) and always pass.
    """
    return entity.root_pos in ("PROPN", "")


def _overlaps_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(not (end <= s or start >= e) for s, e in spans)


def _dedup(entities: list[Entity]) -> list[Entity]:
    seen: set[tuple[str, str]] = set()
    result = []
    for e in entities:
        key = (e.type, e.value)
        if key not in seen:
            seen.add(key)
            result.append(e)
    return result
