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

Post-extraction:  drop_html_entity_artefacts(entities) -> list[Entity]
    Removes entities whose value is an HTML-entity character run (≤30 chars
    containing '&') — quoted-reply markup from undecoded HTML bodies (N9c-html).
"""

from __future__ import annotations

import re

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


def drop_salutation_blocklist(entities: list[Entity]) -> list[Entity]:
    """Remove entities whose value is a known salutation or sign-off phrase (static blocklist)."""
    return [e for e in entities if e.value.strip().lower() not in _SALUTATION_BLOCKLIST]


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


# HTML-entity run fragments (N9c-html pollution):
# Short values (≤30 chars) composed entirely of HTML-entity syntax characters — &, ;, lowercase
# letters, digits, whitespace, # — that also contain at least one '&'.  These arise when
# zkm-eml renders an HTML body with entities left undecoded before NER, so quoted-reply markers
# like &gt;&nbsp; get extracted as ORG entities.  Requiring '&' prevents the regex from
# matching unrelated lowercase strings such as common nouns already handled by other filters.
_RE_HTML_ENTITY_ARTEFACT = re.compile(r"^[&;a-z0-9\s#]+$")
_HTML_ENTITY_MAX_LEN = 30


def drop_html_entity_artefacts(entities: list[Entity]) -> list[Entity]:
    """Remove short HTML-entity character runs extracted as entities from undecoded HTML bodies."""
    return [
        e for e in entities
        if not (
            len(e.value) <= _HTML_ENTITY_MAX_LEN
            and "&" in e.value
            and _RE_HTML_ENTITY_ARTEFACT.match(e.value)
        )
    ]
