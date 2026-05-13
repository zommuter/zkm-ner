"""Model version resolution for extraction-cache key construction."""

from __future__ import annotations

import importlib.metadata


def model_version(model_name: str) -> str:
    """Return an opaque version string for *model_name*.

    Used as part of the extraction-cache key so that upgrading a model
    automatically invalidates cached results.
    """
    if model_name == "gliner":
        try:
            return importlib.metadata.version("gliner")
        except importlib.metadata.PackageNotFoundError:
            return "unknown"
    # spacy (default) — combine both model package versions
    try:
        de = importlib.metadata.version("de-core-news-sm")
        en = importlib.metadata.version("en-core-web-sm")
        return f"de:{de}+en:{en}+textfilter-v5+posfilter-v1+iban-v1+email-v1+phone-v1+url-v1+invoice-v1+tracking-v1+regcode-v1+scope-blocks-v1"
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
