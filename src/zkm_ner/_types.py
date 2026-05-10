"""Shared types for zkm-ner."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Entity:
    """A single entity mention extracted from a document body.

    ``type`` and ``value`` are the only fields written to the amendment record
    via ``as_dict()``.  ``start`` / ``end`` are character offsets used
    internally for pattern-vs-NER span overlap deduplication and are never
    serialised.
    """

    type: str   # e.g. "person", "email_address", "linkedin_profile"
    value: str  # normalised mention string — never a UID

    # Character offsets in the source body.  -1 means unknown / not applicable.
    start: int = field(default=-1, compare=False, repr=False)
    end: int = field(default=-1, compare=False, repr=False)

    def __post_init__(self) -> None:
        # spaCy ent.text can include surrounding newlines when an entity spans
        # a line boundary; strip unconditionally to keep values clean.
        self.value = self.value.strip()

    def as_dict(self) -> dict:
        return {"type": self.type, "value": self.value}
