#!/usr/bin/env python3
"""N9d Stage 2 gate — interactive batch classifier for 'drop' verdicts.

## Usage

    # Step 1: produce the 100-item sample TSV (if not already done)
    uv run python scripts/gate_classify.py --sample

    # Step 2: classify interactively (resumes if interrupted)
    uv run python scripts/gate_classify.py --classify

    # Step 3: compute Gate A/B/C from the completed file
    uv run python scripts/gate_classify.py --gate

## Classification session

Items are presented in batches of ~8, grouped by suspicious_reason + type
so similar items appear together (easier batch decisions).

At each batch prompt:

    legit          real entity wrongly dropped (FP drop — bad)
    own-name       your own name/contact info  (FP drop — bad)
    boilerplate    real org but footer/legal noise (FP drop — bad)
    closed-set-fp  known FP class a heuristic already/could catch (correct)
    open-set-fp    genuine FP not caught by any heuristic (correct)
    split          classify this batch one item at a time
    skip           defer these items to the end
    quit           save and exit (resume later)

## Gate thresholds (docs/meeting-notes/2026-05-11-2316-n9d-llm-verifier-design.md)

    Gate A: FP-drop ≤2%  AND correct-drop ≥60%  →  zkm scrub ner --with-verifier --apply
    Gate B: FP-drop 2–5% OR  correct-drop <60%  →  iterate / adjust
    Gate C: FP-drop ≥5%                         →  close N9d, verifier not safe
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from pathlib import Path

BUCKETS = {"legit", "own-name", "boilerplate", "closed-set-fp", "open-set-fp"}
LEGIT = {"legit", "own-name", "boilerplate"}
CORRECT = {"closed-set-fp", "open-set-fp"}

BUCKET_HINT = (
    "  legit / own-name / boilerplate  →  FP drop (bad)\n"
    "  closed-set-fp / open-set-fp     →  correct drop (good)\n"
    "  split  →  classify one by one\n"
    "  skip   →  defer to end\n"
    "  quit   →  save and exit"
)

# ── ANSI helpers ──────────────────────────────────────────────────────────────

def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"

def _dim(s: str) -> str:
    return f"\033[2m{s}\033[0m"

def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"

def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"

def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


# ── TSV helpers ───────────────────────────────────────────────────────────────

FIELDS = ["#", "type", "value", "suspicious_reason", "context_snippet", "file", "bucket"]


def _load_tsv(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            if row.get("#", "").startswith("#"):
                continue
            rows.append(row)
    return rows


def _save_tsv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


# ── Gate calculation ──────────────────────────────────────────────────────────

def _gate_stats(rows: list[dict]) -> dict:
    classified = [r for r in rows if r.get("bucket", "").strip().lower() in BUCKETS]
    n = len(classified)
    n_legit = sum(1 for r in classified if r["bucket"].strip().lower() in LEGIT)
    n_correct = sum(1 for r in classified if r["bucket"].strip().lower() in CORRECT)
    return {"n": n, "n_legit": n_legit, "n_correct": n_correct,
            "fp_rate": n_legit / n if n else 0,
            "correct_rate": n_correct / n if n else 0}


def _print_gate(stats: dict, total: int) -> None:
    n, fp, cr = stats["n"], stats["fp_rate"], stats["correct_rate"]
    done = _green(f"{n}/{total}") if n == total else _yellow(f"{n}/{total}")
    print(f"  Progress: {done} classified  |  "
          f"FP-drop: {_red(f'{fp:.1%}') if fp > 0.02 else _green(f'{fp:.1%}')}  |  "
          f"correct-drop: {_green(f'{cr:.1%}') if cr >= 0.6 else _yellow(f'{cr:.1%}')}")


# ── Batch grouping ────────────────────────────────────────────────────────────

def _group_batches(rows: list[dict], batch_size: int = 8) -> list[list[dict]]:
    """Group unclassified rows by (suspicious_reason, type), then chunk."""
    unclassified = [r for r in rows if not r.get("bucket", "").strip()]
    # Sort by (suspicious_reason, type) for coherent batches
    unclassified.sort(key=lambda r: (r.get("suspicious_reason", ""), r.get("type", "")))
    return [unclassified[i:i + batch_size] for i in range(0, len(unclassified), batch_size)]


# ── Display helpers ───────────────────────────────────────────────────────────

def _fmt_value(v: str) -> str:
    v = v.replace("\n", "↵")
    return repr(v) if len(v) < 50 else repr(v[:47] + "…")


def _print_batch(batch: list[dict], start_idx: int) -> None:
    print()
    for i, row in enumerate(batch, start_idx):
        reason = _dim(f"({row.get('suspicious_reason', '')})")
        ctx = (row.get("context_snippet") or "").replace("\n", " ")[:72]
        print(f"  {_bold(str(i)):>4}.  [{row['type']:6s}] {_fmt_value(row['value']):<42}  {reason}")
        if ctx:
            print(f"          {_dim(ctx)}")
    print()


# ── Interactive classify ──────────────────────────────────────────────────────

def _prompt(msg: str) -> str:
    try:
        return input(msg).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "quit"


def _classify_one(row: dict, idx: int, total: int) -> str | None:
    """Classify a single row interactively. Returns bucket or None on quit."""
    _print_batch([row], idx)
    print(BUCKET_HINT)
    while True:
        ans = _prompt(f"  [{idx}/{total}] bucket > ")
        if ans == "quit":
            return None
        if ans in BUCKETS:
            return ans
        if ans == "skip":
            return ""
        valid = ", ".join(sorted(BUCKETS)) + ", skip, quit"
        print(f"  Unknown: {ans!r}. Valid: {valid}")


def cmd_classify(args: argparse.Namespace) -> None:
    path = _resolve_tsv(args)
    if not path:
        sys.exit("No sample TSV found. Run --sample first.")

    rows = _load_tsv(path)
    total = len(rows)

    # Index rows by # for O(1) update
    by_num = {r["#"]: r for r in rows}

    print(_bold(f"\n=== N9d Gate Classifier — {path.name} ==="))
    stats = _gate_stats(rows)
    _print_gate(stats, total)

    batches = _group_batches(rows)
    skipped: list[dict] = []

    for batch_idx, batch in enumerate(batches, 1):
        if not batch:
            continue
        n_left = sum(1 for r in rows if not r.get("bucket", "").strip())
        print(_bold(f"\n── Batch {batch_idx}/{len(batches)}  ({n_left} remaining) ──"))

        # Show the batch
        _print_batch(batch, int(batch[0]["#"]))
        print(BUCKET_HINT)

        while True:
            ans = _prompt(f"  Batch bucket > ")

            if ans == "quit":
                _save_tsv(path, rows)
                print(_green(f"\nSaved. Resume with: uv run python scripts/gate_classify.py --classify"))
                return

            if ans == "split":
                # Classify one by one
                for row in batch:
                    if row.get("bucket", "").strip():
                        continue
                    result = _classify_one(row, int(row["#"]), total)
                    if result is None:
                        _save_tsv(path, rows)
                        print(_green("\nSaved. Resume with: uv run python scripts/gate_classify.py --classify"))
                        return
                    by_num[row["#"]]["bucket"] = result
                    if not result:
                        skipped.append(row)
                break

            if ans == "skip":
                skipped.extend(batch)
                break

            if ans in BUCKETS:
                for row in batch:
                    by_num[row["#"]]["bucket"] = ans
                n = len(batch)
                print(_green(f"  ✓ {n} item{'s' if n > 1 else ''} → {ans}"))
                break

            valid = ", ".join(sorted(BUCKETS)) + ", split, skip, quit"
            print(f"  Unknown: {ans!r}. Valid: {valid}")

        # Print running gate after each batch
        stats = _gate_stats(rows)
        _print_gate(stats, total)
        _save_tsv(path, rows)

    # Handle skipped items one by one
    remaining_skipped = [r for r in skipped if not by_num[r["#"]].get("bucket", "").strip()]
    if remaining_skipped:
        print(_bold(f"\n── Deferred items ({len(remaining_skipped)}) — classify one by one ──"))
        for row in remaining_skipped:
            result = _classify_one(row, int(row["#"]), total)
            if result is None:
                _save_tsv(path, rows)
                print(_green("\nSaved. Resume with: uv run python scripts/gate_classify.py --classify"))
                return
            by_num[row["#"]]["bucket"] = result

    _save_tsv(path, rows)
    print(_bold(_green("\n✓ All items classified.")))
    cmd_gate(args)


# ── Sample generation ─────────────────────────────────────────────────────────

def _resolve_store(args: argparse.Namespace) -> Path:
    store = Path(args.store) if getattr(args, "store", None) else Path(
        os.environ.get("ZKM_STORE", Path.home() / "knowledge"))
    if not store.exists():
        sys.exit(f"Store not found: {store}")
    return store


def _resolve_tsv(args: argparse.Namespace) -> Path | None:
    if getattr(args, "tsv", None):
        return Path(args.tsv)
    store = _resolve_store(args)
    # Latest sample TSV under .zkm-state
    candidates = sorted(store.glob(".zkm-state/**/ner-verifier-pilot-*-sample.tsv"), reverse=True)
    return candidates[0] if candidates else None


def _latest_pilot(store: Path) -> Path | None:
    candidates = sorted(store.glob(".zkm-state/ner-verifier-pilot-*.jsonl"), reverse=True)
    return candidates[0] if candidates else None


def cmd_sample(args: argparse.Namespace) -> None:
    store = _resolve_store(args)
    pilot = Path(args.pilot) if getattr(args, "pilot", None) else _latest_pilot(store)
    if pilot is None:
        sys.exit("No pilot JSONL found. Run build_pilot_from_cache.py first.")

    records = [json.loads(l) for l in open(pilot, encoding="utf-8") if l.strip()]
    drops = [r for r in records if r["verdict"] == "drop"]
    if not drops:
        sys.exit("No 'drop' verdicts found in pilot JSONL.")

    random.seed(getattr(args, "seed", 42))

    # Stratified by (suspicious_reason) for diverse sample
    by_reason: dict[str, list] = {}
    for r in drops:
        by_reason.setdefault(r.get("suspicious_reason") or "other", []).append(r)

    sample: list = []
    target = min(100, len(drops))
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

    out = pilot.with_name(pilot.stem + "-sample.tsv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        for i, r in enumerate(sample, 1):
            writer.writerow({
                "#": i,
                "type": r.get("type", ""),
                "value": r.get("value", ""),
                "suspicious_reason": r.get("suspicious_reason", ""),
                "context_snippet": (r.get("context_snippet") or "").replace("\n", " ")[:120],
                "file": r.get("file", ""),
                "bucket": "",
            })

    print(f"Sample of {len(sample)} 'drop' verdicts → {out}")
    print(f"Next: uv run python scripts/gate_classify.py --classify")


# ── Gate report ───────────────────────────────────────────────────────────────

def cmd_gate(args: argparse.Namespace) -> None:
    path = _resolve_tsv(args)
    if not path:
        sys.exit("No sample TSV found.")
    rows = _load_tsv(path)
    stats = _gate_stats(rows)
    n, fp, cr = stats["n"], stats["fp_rate"], stats["correct_rate"]
    total = len(rows)

    unclassified = total - n
    if unclassified:
        print(_yellow(f"Warning: {unclassified}/{total} items still unclassified."), file=sys.stderr)

    print(f"\nSample size:        {n}")
    print(f"FP drops (legit):   {stats['n_legit']}  ({fp:.1%})")
    print(f"Correct drops:      {stats['n_correct']}  ({cr:.1%})")
    print()

    if n < total:
        print(_yellow("Complete classification before applying gate."))
    elif fp >= 0.05:
        print(_red("GATE C") + " — FP-drop ≥5%. Verifier not safe to apply. Close N9d.")
    elif fp <= 0.02 and cr >= 0.60:
        print(_green("GATE A") + " — FP-drop ≤2% AND correct-drop ≥60%. Proceed:")
        print("  zkm scrub ner --with-verifier --apply")
    else:
        print(_yellow("GATE B") + " — Borderline. Review unclear verdicts or adjust thresholds.")

    # Bucket breakdown
    buckets: dict[str, int] = {}
    for r in rows:
        b = r.get("bucket", "").strip().lower()
        if b:
            buckets[b] = buckets.get(b, 0) + 1
    if buckets:
        print("\nBucket breakdown:")
        for b, c in sorted(buckets.items(), key=lambda x: -x[1]):
            bar = "█" * int(c / max(buckets.values()) * 20)
            print(f"  {b:20s}  {c:4d}  {bar}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", default=None)
    p.add_argument("--pilot", default=None, help="Pilot JSONL path (default: latest in store)")
    p.add_argument("--tsv", default=None, help="Sample TSV path (default: latest in store)")
    p.add_argument("--seed", type=int, default=42)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--sample", action="store_true", help="Generate 100-item sample TSV from pilot JSONL")
    mode.add_argument("--classify", action="store_true", help="Interactive batch classification (default)")
    mode.add_argument("--gate", action="store_true", help="Print gate A/B/C result from classified TSV")
    args = p.parse_args()

    if args.sample:
        cmd_sample(args)
    elif args.gate:
        cmd_gate(args)
    else:
        cmd_classify(args)


if __name__ == "__main__":
    main()
