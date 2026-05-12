"""Pattern overlay: deterministic entity extraction.

Runs before NER; pattern spans win on overlap (handled in extract.py).
All extractors return Entity objects with ``start``/``end`` character offsets.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

import phonenumbers
import yaml

from zkm.canonical import amount as _canonical_amount
from zkm_ner._types import Entity

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.ASCII,
)


def extract_emails(body: str) -> list[Entity]:
    return [
        Entity("email_address", m.group(0).lower(), start=m.start(), end=m.end())
        for m in _EMAIL_RE.finditer(body)
    ]


# ---------------------------------------------------------------------------
# Phone numbers
# ---------------------------------------------------------------------------

def extract_phones(body: str, *, region: str = "CH") -> list[Entity]:
    """Extract phone numbers using libphonenumber, default region CH."""
    results = []
    for match in phonenumbers.PhoneNumberMatcher(body, region):
        normalised = phonenumbers.format_number(
            match.number, phonenumbers.PhoneNumberFormat.E164
        )
        results.append(Entity("phone_number", normalised, start=match.start, end=match.end))
    return results


# ---------------------------------------------------------------------------
# URLs, domains, and identity-strong URL patterns
# ---------------------------------------------------------------------------

# Intentionally broad; identity-strong patterns are extracted separately.
_URL_RE = re.compile(
    r"https?://[^\s<>\"{}|\\^`\[\]]{3,}",
    re.IGNORECASE,
)

_LINKEDIN_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_\-%]+)",
    re.IGNORECASE,
)

_GITHUB_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([a-zA-Z0-9_\-]+)(?:[/?#][^\s<>\"]*)?",
    re.IGNORECASE,
)

_STEAM_ID_RE = re.compile(
    r"https?://steamcommunity\.com/(?:id|profiles)/([a-zA-Z0-9_\-/]+)",
    re.IGNORECASE,
)

_TELEGRAM_URL_RE = re.compile(
    r"https?://t\.me/([a-zA-Z][a-zA-Z0-9_]{4,})",
    re.IGNORECASE,
)

_DISCORD_USER_RE = re.compile(
    r"https?://(?:www\.)?discord(?:app)?\.com/users/(\d{17,20})",
    re.IGNORECASE,
)

# Bare @handle: Telegram-style username in text (min 5 chars, letter-first).
# Excludes email addresses (handled above) and mastodon handles (handled below).
_TELEGRAM_BARE_RE = re.compile(
    r"(?<![/@\w])@([a-zA-Z][a-zA-Z0-9_]{4,})(?![@\w])",
)

# Mastodon: @user@domain
_MASTODON_RE = re.compile(
    r"@([a-zA-Z0-9_]+)@([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
)


def extract_urls(body: str) -> list[Entity]:
    """Emit url + org_hint for every HTTP(S) URL that isn't an identity-strong pattern."""
    identity_spans = _identity_strong_spans(body)
    results = []
    for m in _URL_RE.finditer(body):
        url = _strip_trailing_punctuation(m.group(0))
        start, end = m.start(), m.start() + len(url)
        if _overlaps_any(start, end, identity_spans):
            continue
        results.append(Entity("url", url, start=start, end=end))
        domain = _extract_domain(url)
        if domain:
            results.append(Entity("org_hint", domain, start=start, end=end))
    return results


def extract_linkedin(body: str) -> list[Entity]:
    return [
        Entity("linkedin_profile", _strip_trailing_punctuation(m.group(0)),
               start=m.start(), end=m.start() + len(_strip_trailing_punctuation(m.group(0))))
        for m in _LINKEDIN_RE.finditer(body)
    ]


def extract_github(body: str) -> list[Entity]:
    """Extract GitHub profile URLs (single path segment = user; skip org/repo)."""
    results = []
    for m in _GITHUB_RE.finditer(body):
        url = _strip_trailing_punctuation(m.group(0))
        # Drop if a second path segment is present (likely a repo URL)
        path = urllib.parse.urlparse(url).path.strip("/")
        if "/" in path:
            continue
        results.append(Entity("github_profile", url,
                               start=m.start(), end=m.start() + len(url)))
    return results


def extract_social_handles(body: str) -> list[Entity]:
    """Extract Telegram, Discord, Steam, Mastodon handles."""
    results: list[Entity] = []

    for m in _TELEGRAM_URL_RE.finditer(body):
        url = _strip_trailing_punctuation(m.group(0))
        results.append(Entity("social_handle.telegram", url,
                               start=m.start(), end=m.start() + len(url)))

    for m in _DISCORD_USER_RE.finditer(body):
        url = _strip_trailing_punctuation(m.group(0))
        results.append(Entity("social_handle.discord", url,
                               start=m.start(), end=m.start() + len(url)))

    for m in _STEAM_ID_RE.finditer(body):
        url = _strip_trailing_punctuation(m.group(0))
        results.append(Entity("social_handle.steam", url,
                               start=m.start(), end=m.start() + len(url)))

    for m in _MASTODON_RE.finditer(body):
        handle = f"@{m.group(1)}@{m.group(2)}"
        results.append(Entity("social_handle.mastodon", handle,
                               start=m.start(), end=m.end()))

    # Bare @handle — only emit if not already covered by a URL-based telegram match
    telegram_url_spans = [(m.start(), m.end()) for m in _TELEGRAM_URL_RE.finditer(body)]
    for m in _TELEGRAM_BARE_RE.finditer(body):
        if not _overlaps_any(m.start(), m.end(), telegram_url_spans):
            results.append(Entity("social_handle.telegram", m.group(0),
                                   start=m.start(), end=m.end()))

    return results


# ---------------------------------------------------------------------------
# Org gazetteer
# ---------------------------------------------------------------------------

_DEFAULT_GAZETTEER = Path(__file__).parent.parent.parent / "gazetteers" / "orgs.yaml"


def load_gazetteer(path: str | Path | None = None) -> list[dict]:
    """Load gazetteer entries from *path*, falling back to the bundled default."""
    p = Path(path) if path else _DEFAULT_GAZETTEER
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("entries", [])


def extract_gazetteer(body: str, entries: list[dict]) -> list[Entity]:
    """Match gazetteer aliases in *body*; emit canonical name as org entity."""
    results: list[Entity] = []
    for entry in entries:
        canonical = entry["canonical"]
        etype = entry.get("type", "org")
        for alias in entry.get("aliases", []):
            pattern = re.compile(
                r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
                re.IGNORECASE,
            )
            for m in pattern.finditer(body):
                results.append(Entity(etype, canonical, start=m.start(), end=m.end()))
    return results


# ---------------------------------------------------------------------------
# Monetary amounts — DE/CH/EN
# ---------------------------------------------------------------------------

# Multi-char symbols first so the alternation is greedy-correct.
_CURR_SYMS = r"SFr\.|SFr|Fr\.|Fr|€|£|\$|¥"
_CURR_CODES = r"[A-Z]{3}"

# Number body: digits + grouping separators, avoiding consuming the '.' in '.-'.
# \.(?!-) matches a period only when NOT followed by '-', preventing greedy
# consumption of the dot that belongs to the Swiss '.-' suffix.
_AMOUNT_NUM = r"\d(?:['\d,]|\.(?!-))*(?:\.-)?|\d"

# Two alternatives:
#   prefix:  [sign] CURR [sign] number
#   suffix:  [sign] number [space?] CURR
# Negative lookbehind/lookahead prevent matching inside longer tokens.
_AMOUNT_RE = re.compile(
    rf"(?<![A-Za-z\d])"
    rf"(?:"
    rf"(?:[-+]\s*)?(?:{_CURR_SYMS}|{_CURR_CODES})\s*(?:[-+]\s*)?(?:{_AMOUNT_NUM})"
    rf"|"
    rf"(?:[-+]\s*)?(?:{_AMOUNT_NUM})\s*(?:{_CURR_SYMS}|{_CURR_CODES})"
    rf")"
    rf"(?![A-Za-z\d])",
)


def extract_amounts(body: str) -> list[Entity]:
    """Extract monetary amounts; canonical form via ``zkm.canonical.amount``."""
    results: list[Entity] = []
    for m in _AMOUNT_RE.finditer(body):
        raw = m.group(0).strip()
        try:
            decimal_str, currency_code = _canonical_amount(raw)
        except Exception:
            continue
        canonical = decimal_str if decimal_str != raw else None
        results.append(Entity(
            "amount",
            raw,
            canonical=canonical,
            standard="ISO 4217",
            unit=currency_code or None,
            start=m.start(),
            end=m.end(),
        ))
    return results


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------

def extract_all(body: str, *, gazetteer_path: str | None = None) -> list[Entity]:
    """Run all pattern extractors and return merged deduplicated entities."""
    entries = load_gazetteer(gazetteer_path)
    raw: list[Entity] = []
    raw.extend(extract_emails(body))
    raw.extend(extract_phones(body))
    raw.extend(extract_linkedin(body))
    raw.extend(extract_github(body))
    raw.extend(extract_social_handles(body))
    raw.extend(extract_gazetteer(body, entries))
    raw.extend(extract_amounts(body))
    raw.extend(extract_urls(body))
    return raw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRAILING_PUNCT = re.compile(r"[.,;:!?)>\]]+$")


def _strip_trailing_punctuation(s: str) -> str:
    return _TRAILING_PUNCT.sub("", s)


def _extract_domain(url: str) -> str | None:
    try:
        host = urllib.parse.urlparse(url).netloc
        host = re.sub(r":\d+$", "", host)  # strip port
        return re.sub(r"^www\.", "", host) or None
    except Exception:
        return None


def _overlaps_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(not (end <= s or start >= e) for s, e in spans)


def _identity_strong_spans(body: str) -> list[tuple[int, int]]:
    """Spans occupied by identity-strong URL patterns (linkedin, github, etc.)."""
    spans = []
    for pat in (_LINKEDIN_RE, _GITHUB_RE, _STEAM_ID_RE, _TELEGRAM_URL_RE, _DISCORD_USER_RE):
        for m in pat.finditer(body):
            spans.append((m.start(), m.end()))
    return spans
