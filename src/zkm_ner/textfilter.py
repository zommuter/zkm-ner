"""Two-stage text filter for NER pre-processing and post-extraction cleanup.

Pre-strip:  strip_markdown_artefacts(body) -> str
    Removes markdown table separator rows and pure-pipe rows that render as
    noise when email threads are converted to markdown (class 1 pollution).

Post-extraction:  drop_stoplist(entities) -> list[Entity]
    Removes entities whose value matches a closed-set of email header field
    names and subject-line prefixes (class 2+3 pollution).

Post-extraction:  drop_structural_artefacts(entities) -> list[Entity]
    Removes entities whose value consists solely of pipe characters and
    whitespace — inline empty table cells within data rows (class 5 pollution).

Post-extraction:  drop_section_link_artefacts(entities) -> list[Entity]
    Removes entities whose value begins with "Section N]" — broken markdown
    link-target fragments left by the email→markdown converter (class 7 pollution).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from zkm_ner._types import Entity

# Separator rows: e.g. |---|---| or |:--:|:--:| (no data cells)
_RE_SEPARATOR = re.compile(r"^\s*\|[\s|:\-]+\|\s*$")
# Pure-pipe rows: only pipes and whitespace, e.g. "| |" or "||"
_RE_PURE_PIPE = re.compile(r"^\s*\|+(\s*\|+)*\s*$")

_STOPLIST: frozenset[str] = frozenset({
    "from", "to", "cc", "bcc",
    "subject", "betreff",
    "date", "sent", "received",
    "thread",
    "re", "fwd", "wg", "aw",
})

# Multi-word salutation / sign-off phrases extracted by spaCy as PERSON (class 6 pollution).
# Closed set derived from the post-N9c pilot top-30 multi-word PERSON audit (2026-05-11).
# Type-agnostic: matched case-insensitively on the full value string.
_SALUTATION_BLOCKLIST: frozenset[str] = frozenset({
    # Greeting salutations
    "hallo maxine",
    "hallo maxine mustermann",
    "hello maxine",
    "lieber maxine",
    "hallo alexander",
    "hallo herr mustermann",
    "hallo herr",
    "guten tag herr mustermann",
    "guten tag herr",
    "guten morgen herr",
    "lieber herr",
    # Pronoun / phrase fragments
    "du dich",
    "wenn sie",
    # Common email sign-offs (also appear in other entity types)
    "best regards",
    "kind regards",
    "mit freundlichen grüßen",
    "viele grüße",
    "mit besten grüßen",
})

# Greeting/salutation prefixes (lowercased) used for cross-product with user-supplied names.
# Each entry is combined with a user name to generate blocked phrases like "hallo tobias",
# "guten tag herr kienzler", etc.  Bare names are never in this list — only prefix+name pairs
# are generated, so a legitimate "Tobias Kienzler" PERSON entity is never blocked.
_GREETING_PREFIXES: frozenset[str] = frozenset({
    # Informal greetings (DE + EN)
    "hallo", "hello", "hi", "hey",
    # Formal/polite (DE)
    "guten tag", "guten morgen", "guten abend",
    "sehr geehrter herr", "sehr geehrte frau",
    "lieber", "liebe", "liebes",
    "lieber herr", "liebe frau",
    # Honorific without greeting word (DE)
    "herr", "frau",
    # With honorific attached to greeting word
    "hallo herr", "hallo frau",
    "guten tag herr", "guten tag frau",
    # Formal (EN)
    "dear",
})


def build_user_salutations(names: list | str | None) -> frozenset[str]:
    """Return a frozenset of lowercase greeting phrases derived from *names*.

    Accepts a list of strings (from YAML config) or a single string (comma- or
    newline-separated).  Each name form is cross-producted with ``_GREETING_PREFIXES``
    to produce phrases like "hallo tobias", "guten tag herr kienzler".
    Bare names are never included — only prefix+name pairs.
    Returns an empty frozenset when *names* is absent or empty.
    """
    if not names:
        return frozenset()
    if isinstance(names, str):
        raw: Iterable[str] = re.split(r"[,\n]+", names)
    else:
        raw = names
    normalised = [" ".join(n.split()) for n in raw if n and n.strip()]
    if not normalised:
        return frozenset()
    return frozenset(
        f"{prefix} {name}".lower()
        for prefix in _GREETING_PREFIXES
        for name in normalised
    )


# Common-noun and abbreviation false positives from the NER pilot (class 4 pollution).
# Values that spaCy may tag as PROPN in some contexts but are never real entities.
_COMMONNOUN_STOPLIST: frozenset[str] = frozenset({
    "du", "wünschen", "zeit",
    "eur", "chf",
    "utc", "mesz", "cest",
    "internet", "cv", "agb", "hrb",
})


def strip_markdown_artefacts(body: str) -> str:
    """Return *body* with markdown table separator and pure-pipe rows removed."""
    lines = body.splitlines(keepends=True)
    out = []
    for line in lines:
        stripped = line.rstrip("\n")
        if _RE_SEPARATOR.match(stripped) or _RE_PURE_PIPE.match(stripped):
            continue
        out.append(line)
    return "".join(out)


def drop_stoplist(entities: list[Entity]) -> list[Entity]:
    """Return *entities* with stoplist matches removed (type-agnostic, case-insensitive)."""
    return [e for e in entities if e.value.strip().lower() not in _STOPLIST]


def drop_salutation_blocklist(
    entities: list[Entity],
    extra: frozenset[str] = frozenset(),
) -> list[Entity]:
    """Remove entities whose value is a known salutation/sign-off or a user-generated greeting phrase.

    *extra* should be the result of ``build_user_salutations(user_names)``; when omitted
    only the static blocklist applies (preserving existing behaviour).
    """
    blocked = _SALUTATION_BLOCKLIST | extra
    return [e for e in entities if e.value.strip().lower() not in blocked]


def drop_commonnoun_stoplist(entities: list[Entity]) -> list[Entity]:
    """Remove entities matching the common-noun/abbreviation closed set (type-agnostic, case-insensitive)."""
    return [e for e in entities if e.value.strip().lower() not in _COMMONNOUN_STOPLIST]


# Pipe-only / whitespace-only entity values from inline empty table cells (class 5 pollution).
_RE_STRUCTURAL_ARTEFACT = re.compile(r"^[\s|]+$")


def drop_structural_artefacts(entities: list[Entity]) -> list[Entity]:
    """Remove entities whose value is only pipe characters and whitespace (e.g. '| |', '| | |')."""
    return [e for e in entities if not _RE_STRUCTURAL_ARTEFACT.match(e.value)]


# "Section N]" fragments from broken markdown link parsing in zkm-eml (class 7 pollution).
# Anchored at start; trailing content (newlines, continued markdown) is captured by the open match.
_RE_SECTION_LINK_ARTIFACT = re.compile(r"^Section\s+\d+\]")


def drop_section_link_artefacts(entities: list[Entity]) -> list[Entity]:
    """Remove entities whose value begins with 'Section N]' — broken link-target artifacts."""
    return [e for e in entities if not _RE_SECTION_LINK_ARTIFACT.match(e.value)]
