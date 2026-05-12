"""Shared types for zkm-ner."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Entity:
    """A single entity mention extracted from a document body.

    γ-schema fields (``scope``, ``canonical``, ``standard``, ``unit``,
    ``valid``) are written to the amendment record via ``as_dict()``.
    ``start`` / ``end`` are character offsets used internally for
    pattern-vs-NER span overlap deduplication and are never serialised.
    """

    type: str   # e.g. "person", "email_address", "linkedin_profile"
    value: str  # normalised mention string — never a UID

    # γ schema fields
    scope: str = "body"          # extraction source: "body" | "signature" | "salutation" | …
    canonical: str | None = None  # normalised form when it differs from value (e.g. E.164 phone)
    standard: str | None = None   # governing standard for canonical (e.g. "E.164", "ISO 13616")
    unit: str | None = None       # unit for numeric types (e.g. "CHF")
    valid: bool = True            # False when canonical form fails its checksum / format

    # Character offsets in the source body.  -1 means unknown / not applicable.
    start: int = field(default=-1, compare=False, repr=False)
    end: int = field(default=-1, compare=False, repr=False)
    # Root token POS tag from spaCy.  "" for pattern-overlay entities (no NLP context).
    root_pos: str = field(default="", compare=False, repr=False)

    def __post_init__(self) -> None:
        # spaCy ent.text can include surrounding newlines when an entity spans
        # a line boundary; strip unconditionally to keep values clean.
        self.value = self.value.strip()
        if self.canonical is not None and self.canonical == self.value:
            raise ValueError(
                f"Entity.canonical must differ from value; got {self.value!r} for both"
            )

    def as_dict(self) -> dict:
        d: dict = {"scope": self.scope, "type": self.type, "value": self.value}
        if self.canonical is not None:
            d["canonical"] = self.canonical
        if self.standard is not None:
            d["standard"] = self.standard
        if self.unit is not None:
            d["unit"] = self.unit
        if not self.valid:
            d["valid"] = False
        return d
