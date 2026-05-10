"""Two-stage text filter for NER pre-processing and post-extraction cleanup.

Pre-strip:  strip_markdown_artefacts(body) -> str
    Removes markdown table separator rows and pure-pipe rows that render as
    noise when email threads are converted to markdown (class 1 pollution).

Post-extraction:  drop_stoplist(entities) -> list[Entity]
    Removes entities whose value matches a closed-set of email header field
    names and subject-line prefixes (class 2+3 pollution).
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
