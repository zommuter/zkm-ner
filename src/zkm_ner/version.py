"""Model version resolution — stub until N2 implements the backends."""

from __future__ import annotations


def model_version(model_name: str) -> str:
    """Return an opaque version string for *model_name*.

    Used as part of the extraction-cache key so that upgrading a model
    automatically invalidates cached results for that model.

    Implemented in N2 once the actual backends (spaCy / GLiNER) exist.
    """
    _ = model_name
    return "0.0.0-stub"
