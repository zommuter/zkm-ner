"""Heuristic 'suspicious' predicate for NER quality checking.

Flags entities whose value has characteristics associated with false positives
(short values, all-caps, lowercase person names, single-token MISC, etc.).
Used by the pilot analysis script and by the verifier scrub pass.

Dispatch: ``is_suspicious`` routes to a per-type predicate via ``_PREDICATES``.
NER-derived types use name-shape heuristics; pattern-overlay types (email,
phone, url, …) return None because structural validation already happens at
extraction time.  Future value-type extractors (iban, amount) have named stubs
ready to fill in.
"""

from __future__ import annotations

import re
from collections.abc import Callable


# ---------------------------------------------------------------------------
# Per-type predicate functions
# ---------------------------------------------------------------------------


def _name_predicate(value: str) -> str | None:
    stripped = value.strip()
    if len(stripped) <= 2:
        return f"very short ({len(stripped)} chars)"
    if re.fullmatch(r"[\W\d]+", stripped):
        return "no alphabetic content"
    if stripped.isupper() and len(stripped) > 2:
        return "all-caps (possible acronym misclassification)"
    return None


def _person_predicate(value: str) -> str | None:
    reason = _name_predicate(value)
    if reason:
        return reason
    if value.strip()[0].islower():
        return "person value starts lowercase"
    return None


def _misc_predicate(value: str) -> str | None:
    reason = _name_predicate(value)
    if reason:
        return reason
    if len(value.strip().split()) == 1:
        return "single-token MISC (highest noise rate)"
    return None


def _no_suspicion(_value: str) -> str | None:
    return None


def _iban_predicate(_value: str) -> str | None:
    return None


def _amount_predicate(_value: str) -> str | None:
    return None


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_PREDICATES: dict[str, Callable[[str], str | None]] = {
    # NER-derived types
    "person": _person_predicate,
    "org": _name_predicate,
    "loc": _name_predicate,
    "misc": _misc_predicate,
    # Pattern-overlay types — structurally validated at extraction
    "email_address": _no_suspicion,
    "phone_number": _no_suspicion,
    "url": _no_suspicion,
    "org_hint": _no_suspicion,
    "linkedin_profile": _no_suspicion,
    "github_profile": _no_suspicion,
    # Value-type extractor stubs (E6/E7)
    "iban": _iban_predicate,
    "amount": _amount_predicate,
    "invoice_id": _no_suspicion,
    "tracking_id": _no_suspicion,
    "registration_code": _no_suspicion,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_suspicious(entity_type: str, value: str) -> str | None:
    """Return a reason string if the entity looks suspicious, else None.

    Suspicious entities are candidates for LLM verification; they are not
    necessarily false positives.  The predicate is intentionally conservative
    (low precision) — the verifier provides the precision.
    """
    if entity_type.startswith("social_handle."):
        return None
    predicate = _PREDICATES.get(entity_type, _name_predicate)
    return predicate(value)
