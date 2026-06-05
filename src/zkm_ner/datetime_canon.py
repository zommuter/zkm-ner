"""Datetime canonicalisation for zkm-ner — wraps dateparser for NLP DATE/TIME spans.

Converts raw date/time text from spaCy entity spans to ISO 8601 strings,
anchored on the document's own ``date`` frontmatter field for relative expressions.
"""

from __future__ import annotations

from datetime import date, datetime


def canonicalise(
    text: str,
    *,
    relative_base: date | datetime | None = None,
    lang: str | None = None,
) -> str | None:
    """Parse *text* to an ISO 8601 string, or return None if unparseable.

    *relative_base* anchors relative expressions ("Thursday", "morgen") against the
    document's frontmatter ``date``.  Without it, dateparser uses its own default
    (today's date at import time — acceptable for absolute dates, wrong for relatives).

    Both DE and EN are tried when *lang* is ``"de"`` or ``"en"``; other language codes
    constrain the parse to that language only.
    """
    try:
        import dateparser  # soft dependency
    except ImportError:
        return _stdlib_parse(text)

    settings: dict = {"RETURN_AS_TIMEZONE_AWARE": False, "PREFER_DATES_FROM": "future"}
    if relative_base is not None:
        anchor = (
            datetime(relative_base.year, relative_base.month, relative_base.day)
            if isinstance(relative_base, date) and not isinstance(relative_base, datetime)
            else relative_base
        )
        settings["RELATIVE_BASE"] = anchor

    # Use de+en for any unrecognised language — dateparser raises ValueError on unknown codes
    # (e.g. 'no' from langdetect on Norwegian text). DATE spans are often language-neutral.
    languages = [lang] if lang in ("de", "en") else ["de", "en"]

    parsed = dateparser.parse(text, languages=languages, settings=settings)
    if parsed is None:
        return None

    # Return date-only string when no time component was parsed (midnight default)
    if parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0 and parsed.microsecond == 0:
        return parsed.date().isoformat()
    return parsed.isoformat()


# ---------------------------------------------------------------------------


def _stdlib_parse(text: str) -> str | None:
    """Fallback when dateparser is unavailable: try stdlib ISO / EU date parsing."""
    import re
    text = text.strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        pass
    # DD.MM.YYYY or DD/MM/YYYY
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", text)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None
