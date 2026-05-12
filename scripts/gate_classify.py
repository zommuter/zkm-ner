#!/usr/bin/env python3
"""N9d Stage 2 gate — sample 100 'drop' verdicts for human classification.

## What this script does

Reads the pilot JSONL produced by build_pilot_from_cache.py (or the live
scrub run), picks a stratified random sample of 100 'drop' verdicts, and
writes them to a human-readable TSV file for classification.

## What YOU need to do

1. Run this script to produce the TSV:
       uv run python scripts/gate_classify.py

2. Open the TSV in any spreadsheet or text editor.
   Add a 'bucket' column with one of these 5 values per row:

       legit          — real entity the verifier wrongly dropped (FP drop)
       own-name       — your own name/contact info (treat as legit for gate)
       boilerplate    — legal/footer boilerplate; real org but low-signal (treat as legit)
       closed-set-fp  — a known FP class already in a stoplist (correct drop, could be heuristic)
       open-set-fp    — genuine FP not caught by any heuristic (correct drop, verifier earns its keep)

3. Save the classified TSV alongside the original (same path + '-classified').

4. Run this script again with --gate to compute Gate A/B/C:
       uv run python scripts/gate_classify.py --gate PATH-classified.tsv

## Gate thresholds (from docs/meeting-notes/2026-05-11-2316-n9d-llm-verifier-design.md)

   Gate A: FP-drop-of-legit ≤2%  AND  correct-drop ≥60%  →  proceed with --apply
   Gate B: FP-drop-of-legit 2–5% OR   correct-drop <60%  →  iterate / adjust
   Gate C: FP-drop-of-legit ≥5%                          →  close N9d, verifier not safe

   FP-drop-of-legit = (legit + own-name + boilerplate) / total_sample
   correct-drop     = (closed-set-fp + open-set-fp)   / total_sample
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path


def _latest_pilot(store: Path) -> Path | None:
    candidates = sorted(store.glob(".zkm-state/ner-verifier-pilot-*.jsonl"), reverse=True)
    return candidates[0] if candidates else None


def cmd_sample(args: argparse.Namespace) -> None:
    import os
    store = Path(args.store) if args.store else Path(os.environ.get("ZKM_STORE", Path.home() / "knowledge"))
    pilot = Path(args.pilot) if args.pilot else _latest_pilot(store)
    if pilot is None:
        sys.exit("No pilot JSONL found. Run build_pilot_from_cache.py first.")

    records = [json.loads(l) for l in open(pilot, encoding="utf-8") if l.strip()]
    drops = [r for r in records if r["verdict"] == "drop"]
    if len(drops) < 100:
        print(f"Warning: only {len(drops)} drop records — using all of them.", file=sys.stderr)

    # Stratified by suspicious_reason to get diverse sample
    by_reason: dict[str, list] = {}
    for r in drops:
        by_reason.setdefault(r.get("suspicious_reason") or "other", []).append(r)

    sample: list = []
    target = min(100, len(drops))
    # Round-robin across strata
    keys = list(by_reason.keys())
    iters = {k: iter(random.sample(v, len(v))) for k, v in by_reason.items()}
    while len(sample) < target:
        progress = False
        for k in keys:
            if len(sample) >= target:
                break
            try:
                sample.append(next(iters[k]))
                progress = True
            except StopIteration:
                pass
        if not progress:
            break

    random.shuffle(sample)

    out = Path(args.out) if args.out else pilot.with_suffix("").with_suffix("") / (pilot.stem + "-sample.tsv")
    out.parent.mkdir(parents=True, exist_ok=True)
    # If out ends up as a directory somehow, fix it
    if str(args.out or "").endswith(".tsv") or str(out).endswith(".tsv"):
        pass
    else:
        out = pilot.with_name(pilot.stem + "-sample.tsv")

    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["#", "type", "value", "suspicious_reason", "context_snippet", "file", "bucket"])
        for i, r in enumerate(sample, 1):
            writer.writerow([
                i,
                r.get("type", ""),
                r.get("value", ""),
                r.get("suspicious_reason", ""),
                (r.get("context_snippet") or "")[:80].replace("\n", " "),
                r.get("file", ""),
                "",  # <- fill this in
            ])

    print(f"Sample of {len(sample)} 'drop' verdicts written to:\n  {out}")
    print()
    print("Instructions:")
    print("  Fill in the 'bucket' column with one of:")
    print("    legit        — real entity wrongly dropped")
    print("    own-name     — your own name/contact (counts as legit)")
    print("    boilerplate  — real org but footer/legal noise (counts as legit)")
    print("    closed-set-fp — known FP class (correct drop)")
    print("    open-set-fp   — genuine FP, no heuristic catches it (correct drop)")
    print()
    print(f"Then run:  uv run python scripts/gate_classify.py --gate {out}")


def cmd_gate(args: argparse.Namespace) -> None:
    path = Path(args.gate)
    if not path.exists():
        sys.exit(f"File not found: {path}")

    LEGIT = {"legit", "own-name", "boilerplate"}
    CORRECT = {"closed-set-fp", "open-set-fp"}

    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            if row.get("#", "").startswith("#"):
                continue
            rows.append(row)

    classified = [r for r in rows if r.get("bucket", "").strip()]
    unclassified = len(rows) - len(classified)
    if unclassified:
        print(f"Warning: {unclassified} rows have no bucket — excluded from gate.", file=sys.stderr)

    n = len(classified)
    if n == 0:
        sys.exit("No classified rows found. Fill in the 'bucket' column first.")

    n_legit = sum(1 for r in classified if r["bucket"].strip().lower() in LEGIT)
    n_correct = sum(1 for r in classified if r["bucket"].strip().lower() in CORRECT)
    n_unknown = n - n_legit - n_correct

    fp_rate = n_legit / n
    correct_rate = n_correct / n

    print(f"Sample size:        {n}")
    print(f"Legit (FP drops):   {n_legit}  ({fp_rate:.1%})")
    print(f"Correct drops:      {n_correct}  ({correct_rate:.1%})")
    if n_unknown:
        print(f"Unknown buckets:    {n_unknown}  (check spelling)")
    print()

    if fp_rate >= 0.05:
        print("GATE C — FP-drop-of-legit ≥5%. Verifier not safe. Close N9d.")
    elif fp_rate <= 0.02 and correct_rate >= 0.60:
        print("GATE A — FP-drop-of-legit ≤2% AND correct-drop ≥60%. Proceed with --apply.")
        print("  Next: zkm scrub ner --with-verifier --apply")
    else:
        print("GATE B — Borderline. Iterate: review unclear verdicts, adjust prompt or thresholds.")

    # Breakdown by bucket
    buckets: dict[str, int] = {}
    for r in classified:
        b = r["bucket"].strip().lower()
        buckets[b] = buckets.get(b, 0) + 1
    print()
    print("Bucket breakdown:")
    for b, c in sorted(buckets.items(), key=lambda x: -x[1]):
        print(f"  {b:20s}  {c:4d}  ({c/n:.1%})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", default=None)
    parser.add_argument("--pilot", default=None, help="Path to pilot JSONL (default: latest in store)")
    parser.add_argument("--out", default=None, help="Output TSV path")
    parser.add_argument("--gate", default=None, metavar="TSV", help="Compute gate from a classified TSV")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    if args.gate:
        cmd_gate(args)
    else:
        cmd_sample(args)


if __name__ == "__main__":
    main()
