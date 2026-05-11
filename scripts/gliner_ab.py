"""GLiNER A/B comparison — measures FP reduction vs spaCy without touching frontmatter.

Reads a list of md file paths (--files or stdin, one per line), runs
extract() with both backends, and writes a delta JSONL for analysis.

Usage:
    # Targeted FP-file sample:
    git -C ~/knowledge grep -rl "Hallo Tobias" -- '*.md' | \\
        python gliner_ab.py --store ~/knowledge

    # Explicit file list:
    python gliner_ab.py --store ~/knowledge --files filelist.txt

Output: <store>/.zkm-state/gliner-ab-<ISO8601>.jsonl
        Per-file FP-string survival summary printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_FP_STRINGS = {
    "hallo tobias",
    "hallo tobias kienzler",
    "hello tobias",
    "hallo herr kienzler",
    "hallo herr",
    "guten tag herr kienzler",
    "guten tag herr",
    "lieber herr",
    "du dich",
    "wenn sie",
    "best regards",
    "kind regards",
    "mit freundlichen grüßen",
    "viele grüße",
}


def _load_body(md_path: Path) -> str:
    text = md_path.read_text(errors="replace")
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text[end + 4:] if end != -1 else text


def _is_fp(value: str) -> bool:
    return value.strip().lower() in _FP_STRINGS


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="GLiNER vs spaCy A/B comparison")
    parser.add_argument("--store", default="", help="Store path (default: $ZKM_STORE or ~/knowledge)")
    parser.add_argument("--files", default="", help="File with md paths (one per line); default: stdin")
    parser.add_argument("--out", default="", help="Output JSONL path (default: <store>/.zkm-state/gliner-ab-<ts>.jsonl)")
    args = parser.parse_args(argv)

    store_str = args.store or os.environ.get("ZKM_STORE", "") or str(Path.home() / "knowledge")
    store = Path(store_str).expanduser().resolve()

    if args.files:
        paths = [store / p.strip() if not Path(p.strip()).is_absolute() else Path(p.strip())
                 for p in Path(args.files).read_text().splitlines() if p.strip()]
    else:
        paths = [store / p.strip() if not Path(p.strip()).is_absolute() else Path(p.strip())
                 for p in sys.stdin.read().splitlines() if p.strip()]

    if not paths:
        print("ERROR: no file paths provided (--files or stdin)", file=sys.stderr)
        sys.exit(1)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else store / ".zkm-state" / f"gliner-ab-{ts}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Lazy import — must be inside zkm-ner venv
    plugin_root = Path(__file__).parent.parent
    _venv_site = list((plugin_root / ".venv").glob("lib/python*/site-packages"))
    if _venv_site:
        sys.path.insert(0, str(_venv_site[0]))
    sys.path.insert(0, str(plugin_root / "src"))

    from zkm_ner.extract import extract

    spacy_fps: Counter[str] = Counter()
    gliner_fps: Counter[str] = Counter()
    total = len(paths)

    with out_path.open("w") as fh:
        for i, md_path in enumerate(paths, 1):
            print(f"\r  {i}/{total} {md_path.name[:40]:<40}", end="", file=sys.stderr, flush=True)
            if not md_path.exists():
                continue
            body = _load_body(md_path)

            spacy_ents = [e.as_dict() if hasattr(e, "as_dict") else {"type": e.type, "value": e.value}
                          for e in extract(body, model="spacy")]
            gliner_ents = [e.as_dict() if hasattr(e, "as_dict") else {"type": e.type, "value": e.value}
                           for e in extract(body, model="gliner")]

            spacy_fp_hits = [e for e in spacy_ents if _is_fp(e["value"])]
            gliner_fp_hits = [e for e in gliner_ents if _is_fp(e["value"])]

            for e in spacy_fp_hits:
                spacy_fps[e["value"].strip().lower()] += 1
            for e in gliner_fp_hits:
                gliner_fps[e["value"].strip().lower()] += 1

            fh.write(json.dumps({
                "path": str(md_path),
                "spacy_entities": spacy_ents,
                "gliner_entities": gliner_ents,
                "spacy_fps": spacy_fp_hits,
                "gliner_fps": gliner_fp_hits,
            }, ensure_ascii=False) + "\n")

    print(f"\r  done — {total} files processed{' ' * 30}", file=sys.stderr)
    print(f"\nOutput: {out_path}\n")

    # Summary
    all_fps = sorted(spacy_fps | gliner_fps, key=lambda k: -(spacy_fps[k]))
    print(f"{'FP string':<40} {'spaCy':>6} {'GLiNER':>6}  {'reduction':>10}")
    print("-" * 68)
    for fp in all_fps:
        s, g = spacy_fps[fp], gliner_fps[fp]
        pct = f"{100 * (1 - g / s):.0f}%" if s else "n/a"
        print(f"  {fp!r:<38} {s:>6,} {g:>6,}  {pct:>10}")

    print()
    total_spacy = sum(spacy_fps.values())
    total_gliner = sum(gliner_fps.values())
    if total_spacy:
        overall_pct = 100 * (1 - total_gliner / total_spacy)
        print(f"  Overall FP reduction: {overall_pct:.0f}%  ({total_spacy:,} → {total_gliner:,})")


if __name__ == "__main__":
    main()
