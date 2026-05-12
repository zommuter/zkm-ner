"""Heuristic 'suspicious' predicate for NER quality checking.

Flags entities whose value has characteristics associated with false positives
(short values, all-caps, lowercase person names, single-token MISC, etc.).
Used by the pilot analysis script and by the verifier scrub pass.
"""

from __future__ import annotations

import re


def is_suspicious(entity_type: str, value: str) -> str | None:
    """Return a reason string if the entity looks suspicious, else None.

    Suspicious entities are candidates for LLM verification; they are not
    necessarily false positives.  The predicate is intentionally conservative
    (low precision) — the verifier provides the precision.
    """
    stripped = value.strip()
    if len(stripped) <= 2:
        return f"very short ({len(stripped)} chars)"
    if entity_type == "misc" and len(stripped.split()) == 1:
        return "single-token MISC (highest noise rate)"
    if re.fullmatch(r"[\W\d]+", stripped):
        return "no alphabetic content"
    if stripped.isupper() and len(stripped) > 2:
        return "all-caps (possible acronym misclassification)"
    # spaCy PER often misclassifies German adjectives/verbs as persons — flag
    # single tokens starting with lowercase after sentence-start stripping.
    if entity_type == "person" and stripped[0].islower():
        return "person value starts lowercase"
    return None
