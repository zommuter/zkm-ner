"""NER pilot analysis — reads entity frontmatter from the store and reports:

  - entity-type histogram
  - top-N values per type
  - suspicious-value dump (low-confidence proxy)

Usage (via pilot.sh or directly):
    python pilot.py [--store PATH] [--top N] [--review PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Add the plugin src/ to sys.path so zkm_ner is importable when running as a script.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zkm_ner.suspicious import is_suspicious as _is_suspicious_fn


def _is_suspicious(entity_type: str, value: str) -> str | None:
    """Return a reason string if the entity looks suspicious, else None."""
    return _is_suspicious_fn(entity_type, value)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_md_entities(md_path: Path) -> list[dict]:
    """Return the entities list from a single md file's frontmatter."""
    text = md_path.read_text(errors="replace")
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end == -1:
        return []
    fm_block = text[3:end]
    try:
        import yaml  # type: ignore[import-untyped]
        fm = yaml.safe_load(fm_block) or {}
    except Exception:
        return []
    entities = fm.get("entities") or []
    if not isinstance(entities, list):
        return []
    return [e for e in entities if isinstance(e, dict) and "type" in e and "value" in e]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="zkm-ner pilot analysis")
    parser.add_argument("--store", default="", help="Store path (default: $ZKM_STORE or ~/knowledge)")
    parser.add_argument("--top", type=int, default=20, help="Top-N values per type (default: 20)")
    parser.add_argument("--review", default="", help="Write suspicious entities to this JSONL (default: <store>/.zkm-state/ner-pilot-review-YYYYMMDD-HHMM.jsonl)")
    args = parser.parse_args(argv)

    import os
    store_str = args.store or os.environ.get("ZKM_STORE", "") or str(Path.home() / "knowledge")
    store = Path(store_str).expanduser().resolve()

    if not store.exists():
        print(f"ERROR: store not found: {store}", file=sys.stderr)
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d-%H%M")
    review_path = Path(args.review) if args.review else store / ".zkm-state" / f"ner-pilot-review-{ts}.jsonl"

    # -----------------------------------------------------------------------
    # Scan
    # -----------------------------------------------------------------------
    type_counter: Counter[str] = Counter()
    value_counter: defaultdict[str, Counter[str]] = defaultdict(Counter)
    suspicious: list[dict] = []
    doc_count = 0
    enriched_count = 0

    md_files = sorted(store.rglob("*.md"))
    total = len(md_files)

    for i, md_path in enumerate(md_files, 1):
        if i % 5000 == 0 or i == total:
            print(f"\r  scanning {i}/{total} …", end="", file=sys.stderr, flush=True)
        doc_count += 1
        entities = _parse_md_entities(md_path)
        if entities:
            enriched_count += 1
        for e in entities:
            etype = e["type"]
            evalue = e["value"]
            type_counter[etype] += 1
            value_counter[etype][evalue] += 1
            reason = _is_suspicious(etype, evalue)
            if reason:
                suspicious.append({
                    "type": etype,
                    "value": evalue,
                    "reason": reason,
                    "doc": str(md_path.relative_to(store)),
                })

    print(f"\r  scanned {doc_count} docs, {enriched_count} with entities      ", file=sys.stderr)
    print()

    # -----------------------------------------------------------------------
    # Entity-type histogram
    # -----------------------------------------------------------------------
    total_entities = sum(type_counter.values())
    print(f"=== Entity-type histogram ({total_entities:,} total mentions) ===\n")
    for etype, count in sorted(type_counter.items(), key=lambda x: -x[1]):
        bar = "#" * min(50, count * 50 // max(type_counter.values()))
        pct = 100 * count / total_entities if total_entities else 0
        print(f"  {etype:<22} {count:>7,}  {pct:5.1f}%  {bar}")
    print()

    # -----------------------------------------------------------------------
    # Top-N values per type
    # -----------------------------------------------------------------------
    n = args.top
    print(f"=== Top-{n} values per entity type ===\n")
    for etype in sorted(value_counter, key=lambda t: -type_counter[t]):
        counter = value_counter[etype]
        print(f"  [{etype}] ({len(counter):,} distinct values)")
        for value, cnt in counter.most_common(n):
            print(f"    {cnt:>6,}x  {value!r}")
        print()

    # -----------------------------------------------------------------------
    # Multi-word person values (salutation / FP candidates)
    # -----------------------------------------------------------------------
    mw_persons = [
        (v, c) for v, c in value_counter["person"].most_common()
        if len(v.split()) >= 2
    ][:30]
    if mw_persons:
        print(f"=== Top-30 multi-word person values (salutation / FP candidates) ===\n")
        for value, cnt in mw_persons:
            print(f"    {cnt:>6,}x  {value!r}")
        print()

    # -----------------------------------------------------------------------
    # Suspicious-value dump
    # -----------------------------------------------------------------------
    print(f"=== Suspicious values ({len(suspicious):,} flagged) ===\n")
    reason_groups: defaultdict[str, list[dict]] = defaultdict(list)
    for entry in suspicious:
        reason_groups[entry["reason"]].append(entry)
    for reason, entries in sorted(reason_groups.items()):
        print(f"  [{reason}]  ({len(entries)} entries)")
        for entry in entries[:10]:
            print(f"    {entry['type']:<22} {entry['value']!r:<40}  {entry['doc']}")
        if len(entries) > 10:
            print(f"    … and {len(entries) - 10} more")
        print()

    # -----------------------------------------------------------------------
    # Write review file
    # -----------------------------------------------------------------------
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("w") as fh:
        for entry in suspicious:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"Review file written: {review_path}  ({len(suspicious):,} entries)")


if __name__ == "__main__":
    main()
