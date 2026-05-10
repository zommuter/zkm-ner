"""Entity extractor — pattern overlay + spaCy NER (+ optional GLiNER).

Implemented in N2. This stub satisfies the import contract for the scaffold.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Entity:
    type: str
    value: str
    # optional extras written to the amendment record as-is
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d: dict = {"type": self.type, "value": self.value}
        d.update(self.extra)
        return d


def extract(
    body: str,
    *,
    lang: str | None = None,
    model: str = "spacy",
    gazetteer_path: str | None = None,
) -> list[Entity]:
    """Return entity mentions extracted from *body*.

    Not yet implemented — returns empty list until N2 lands.
    """
    _ = (body, lang, model, gazetteer_path)
    return []
