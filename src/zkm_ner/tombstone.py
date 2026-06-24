"""Per-store tombstone store for removed entities (id:0566).

Decision D1 (zkm meeting 2026-06-23-1807): the extraction cache stays
immutable / single-writer.  ``scrub(dry_run=False)`` instead records a
tombstone per removed entity keyed on ``(scope, type, value)``.
``convert`` (id:fa5a) then filters the cached set through these tombstones
before asserting the result via ``emit_set``, preventing resurrection on
the next full-sweep cache-hit path.

Storage: a single JSONL file at ``<store>/.zkm-state/tombstones.jsonl``.
Each line is a JSON object ``{"scope": ..., "type": ..., "value": ...}``.
Set semantics are enforced in memory on read; ``add()`` appends only when
the triple is not already present.  No GC until list growth is observed
(observe-first design heuristic).
"""

from __future__ import annotations

import json
from pathlib import Path


_STATE_DIR = ".zkm-state"
_TOMBSTONE_FILE = "tombstones.jsonl"


class TombstoneStore:
    """Persistent per-store set of ``(scope, type, value)`` tombstones.

    Parameters
    ----------
    store_path:
        Root directory of the zkm store (contains ``.zkm-state/``).
    """

    def __init__(self, store_path: Path) -> None:
        self._state_dir = store_path / _STATE_DIR
        self._path = self._state_dir / _TOMBSTONE_FILE
        self._entries: set[tuple[str, str, str]] = set()
        self._loaded = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                self._entries.add((obj["scope"], obj["type"], obj["value"]))
            except (json.JSONDecodeError, KeyError):
                pass  # corrupt line — skip (observe-first)

    def _persist(self, scope: str, type_: str, value: str) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"scope": scope, "type": type_, "value": value}, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, scope: str, type_: str, value: str) -> None:
        """Record ``(scope, type, value)`` as tombstoned (idempotent)."""
        self._ensure_loaded()
        key = (scope, type_, value)
        if key not in self._entries:
            self._entries.add(key)
            self._persist(scope, type_, value)

    def is_tombstoned(self, scope: str, type_: str, value: str) -> bool:
        """Return True if the triple has been tombstoned."""
        self._ensure_loaded()
        return (scope, type_, value) in self._entries

    def all(self):  # noqa: A003
        """Yield all tombstoned ``(scope, type, value)`` triples."""
        self._ensure_loaded()
        yield from self._entries
