"""GLiNER backend for zkm-ner (optional extra).

Install with: pip install zkm-ner[gliner]
Activate with: ZKM_NER_MODEL=gliner

Output schema is identical to the spaCy backend so callers are backend-agnostic.

**Truncation limit:** urchade/gliner_multi-v2.1 truncates input at 384 tokens
(~2800 chars). Document content beyond that point is silently ignored.
A/B testing against spaCy (N9d-α, 2026-05-11) showed that on short emails
(<300 tokens) GLiNER produces +14% more entities than spaCy, not fewer —
the apparent FP reduction seen on long emails is a truncation artifact.
Recommended only for short-document corpora; spaCy is the correct default
for mixed-length stores such as mail archives.
"""

from __future__ import annotations

from functools import lru_cache

from zkm_ner._types import Entity

_LABELS = ["person", "org", "loc", "misc"]


@lru_cache(maxsize=2)
def _load_model(model_name: str):
    try:
        from gliner import GLiNER  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "GLiNER is not installed. "
            "Install the optional extra: pip install zkm-ner[gliner]"
        ) from exc
    return GLiNER.from_pretrained(model_name)


def extract_gliner(
    body: str,
    *,
    lang: str | None = None,  # unused — GLiNER is multilingual
    model_name: str = "urchade/gliner_multi-v2.1",
) -> list[Entity]:
    """Run GLiNER NER on *body* and return entity mentions."""
    _ = lang
    if not body.strip():
        return []
    model = _load_model(model_name)
    predictions = model.predict_entities(body, _LABELS)
    return [
        Entity(p["label"], p["text"], start=p["start"], end=p["end"])
        for p in predictions
    ]
