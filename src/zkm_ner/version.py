"""Model version resolution for extraction-cache key construction."""

from __future__ import annotations

import importlib.metadata


def model_version(model_name: str, *, user_names_hash: str = "") -> str:
    """Return an opaque version string for *model_name*.

    Used as part of the extraction-cache key so that upgrading a model or
    changing runtime config (e.g. user_names) automatically invalidates cached
    results.  *user_names_hash* should be the first 8 hex chars of the SHA-256
    of the sorted, normalised user_names list; omit (or pass empty string) when
    no user names are configured.
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
        base = f"de:{de}+en:{en}+textfilter-v6+posfilter-v1+iban-v1+email-v1+phone-v1+url-v1+invoice-v1+tracking-v1+regcode-v1+scope-blocks-v1"
        if user_names_hash:
            return f"{base}+usernames:{user_names_hash}"
        return base
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
