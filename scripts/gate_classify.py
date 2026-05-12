#!/usr/bin/env python3
"""N9d Stage 2 gate — interactive batch classifier for 'drop' verdicts.

## Usage

    # Step 1: produce the 100-item sample TSV (if not already done)
    uv run python scripts/gate_classify.py --sample

    # Step 2: classify interactively — single-key presses, no Enter needed
    uv run python scripts/gate_classify.py --classify

    # Step 3: compute Gate A/B/C from the completed file
    uv run python scripts/gate_classify.py --gate

## Keys  (question: "was the verifier RIGHT to drop this?")

  Verifier was WRONG — this is a real entity it shouldn't have dropped:
    1  real-entity    a genuine person/org/place the verifier killed
    2  my-own-info    your own name, email, phone number
    3  real-but-noisy a real org/name buried in legal footer or boilerplate

  Verifier was CORRECT — this is junk that should be removed:
    4  correct-drop   it's junk, the verifier was right to drop it

  Navigation:
    s  split   classify this batch item by item
    k  skip    defer to end
    q  quit    save and exit (resumes next time)

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
import termios
import tty
from pathlib import Path

# ── Key→bucket mapping ────────────────────────────────────────────────────────

KEY_MAP = {
    "1": "real-entity",
    "2": "my-own-info",
    "3": "real-but-noisy",
    "4": "correct-drop",
    "s": "split",
    "k": "skip",
    "q": "quit",
}

LEGIT   = {"real-entity", "my-own-info", "real-but-noisy"}
CORRECT = {"correct-drop"}
BUCKETS = LEGIT | CORRECT

KEY_HINT = (
    " WRONG drop → [1] real-entity  [2] my-own-info  [3] real-but-noisy\n"
    " RIGHT drop → [4] correct-drop  (junk, verifier was right)\n"
    "              [s] split  [k] skip  [q] quit"
)

# ── Single-keypress input ─────────────────────────────────────────────────────

def _getch() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def _read_key(valid: set[str]) -> str:
    while True:
        ch = _getch().lower()
        if ch == "\x03":   # Ctrl-C
            return "quit"
        if ch in valid:
            return ch

# ── ANSI helpers ──────────────────────────────────────────────────────────────

def _bold(s: str) -> str:   return f"\033[1m{s}\033[0m"
def _dim(s: str) -> str:    return f"\033[2m{s}\033[0m"
def _green(s: str) -> str:  return f"\033[32m{s}\033[0m"
def _red(s: str) -> str:    return f"\033[31m{s}\033[0m"
def _yellow(s: str) -> str: return f"\033[33m{s}\033[0m"
def _cyan(s: str) -> str:   return f"\033[36m{s}\033[0m"

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

# ── Gate stats ────────────────────────────────────────────────────────────────

def _gate_stats(rows: list[dict]) -> dict:
    classified = [r for r in rows if r.get("bucket", "").strip().lower() in BUCKETS]
    n = len(classified)
    n_legit   = sum(1 for r in classified if r["bucket"].strip().lower() in LEGIT)
    n_correct = sum(1 for r in classified if r["bucket"].strip().lower() in CORRECT)
    return {"n": n, "n_legit": n_legit, "n_correct": n_correct,
            "fp_rate":      n_legit   / n if n else 0.0,
            "correct_rate": n_correct / n if n else 0.0}


def _print_gate(stats: dict, total: int) -> None:
    n, fp, cr = stats["n"], stats["fp_rate"], stats["correct_rate"]
    done = _green(f"{n}/{total}") if n == total else _yellow(f"{n}/{total}")
    fp_s  = _red(f"{fp:.1%}")    if fp  > 0.02 else _green(f"{fp:.1%}")
    cr_s  = _green(f"{cr:.1%}")  if cr  >= 0.60 else _yellow(f"{cr:.1%}")
    print(f"  {done} classified  |  FP-drop: {fp_s}  |  correct-drop: {cr_s}")

# ── Batch grouping ────────────────────────────────────────────────────────────

def _group_batches(rows: list[dict], batch_size: int = 8) -> list[list[dict]]:
    unclassified = [r for r in rows if not r.get("bucket", "").strip()]
    unclassified.sort(key=lambda r: (r.get("suspicious_reason", ""), r.get("type", "")))
    return [unclassified[i:i + batch_size] for i in range(0, len(unclassified), batch_size)]

# ── Display ───────────────────────────────────────────────────────────────────

def _fmt_value(v: str) -> str:
    v = v.replace("\n", "↵").replace("\r", "")
    if len(v) > 46:
        v = v[:43] + "…"
    return f"{v!r}"


def _print_batch(batch: list[dict]) -> None:
    print()
    for row in batch:
        reason = _dim(f"({row.get('suspicious_reason', '')})")
        ctx = (row.get("context_snippet") or "").replace("\n", " ").strip()[:72]
        num = _cyan(f"{row['#']:>3}.")
        print(f"  {num}  [{row['type']:6s}] {_fmt_value(row['value']):<46}  {reason}")
        if ctx:
            print(f"           {_dim(ctx)}")
    print()

# ── Classify one item ─────────────────────────────────────────────────────────

def _classify_one(row: dict, idx: int, total: int) -> str | None:
    """Returns bucket string, '' for skip, or None for quit."""
    _print_batch([row])
    print(KEY_HINT, flush=True)
    print(f"  [{idx}/{total}] ", end="", flush=True)
    ch = _read_key(set(KEY_MAP))
    bucket = KEY_MAP[ch]
    if bucket == "quit":
        print("q")
        return None
    if bucket == "skip":
        print("k  (skipped)")
        return ""
    if bucket == "split":
        # In single-item mode, split means nothing — re-prompt
        return _classify_one(row, idx, total)
    print(f"{ch}  → {_bold(bucket)}")
    return bucket

# ── Main classify loop ────────────────────────────────────────────────────────

def cmd_classify(args: argparse.Namespace) -> None:
    path = _resolve_tsv(args)
    if not path:
        sys.exit("No sample TSV found. Run --sample first.")

    rows = _load_tsv(path)
    total = len(rows)
    by_num = {r["#"]: r for r in rows}

    print(_bold(f"\n=== N9d Gate Classifier — {path.name} ==="))
    stats = _gate_stats(rows)
    _print_gate(stats, total)

    batches = _group_batches(rows)
    skipped: list[dict] = []
    n_batches = len(batches)

    for batch_idx, batch in enumerate(batches, 1):
        if not batch:
            continue
        n_left = sum(1 for r in rows if not r.get("bucket", "").strip())
        print(_bold(f"\n── Batch {batch_idx}/{n_batches}  ({n_left} unclassified) ──"))
        _print_batch(batch)
        print(KEY_HINT, flush=True)
        print("  Batch > ", end="", flush=True)

        ch = _read_key(set(KEY_MAP))
        bucket = KEY_MAP[ch]
        print(ch)  # echo

        if bucket == "quit":
            _save_tsv(path, rows)
            print(_green("Saved. Resume: uv run python scripts/gate_classify.py --classify"))
            return

        if bucket == "skip":
            skipped.extend(batch)
            print(_dim("  (batch skipped)"))

        elif bucket == "split":
            print(_dim("  (splitting…)"))
            for row in batch:
                if row.get("bucket", "").strip():
                    continue
                result = _classify_one(row, int(row["#"]), total)
                if result is None:
                    _save_tsv(path, rows)
                    print(_green("Saved. Resume: uv run python scripts/gate_classify.py --classify"))
                    return
                by_num[row["#"]]["bucket"] = result
                if not result:
                    skipped.append(row)

        else:
            for row in batch:
                by_num[row["#"]]["bucket"] = bucket
            n = len(batch)
            print(f"  {_green('✓')} {n} item{'s' if n > 1 else ''} → {_bold(bucket)}")

        stats = _gate_stats(rows)
        _print_gate(stats, total)
        _save_tsv(path, rows)

    # Deferred items — one by one
    remaining = [r for r in skipped if not by_num[r["#"]].get("bucket", "").strip()]
    if remaining:
        print(_bold(f"\n── Deferred: {len(remaining)} items ──"))
        for row in remaining:
            result = _classify_one(row, int(row["#"]), total)
            if result is None:
                _save_tsv(path, rows)
                print(_green("Saved. Resume: uv run python scripts/gate_classify.py --classify"))
                return
            by_num[row["#"]]["bucket"] = result
        _save_tsv(path, rows)

    print(_bold(_green("\n✓ All classified.")))
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
        print(_yellow(f"Warning: {unclassified}/{total} items unclassified."), file=sys.stderr)

    print(f"\nSample: {n}/{total}  |  FP-drop: {fp:.1%}  |  correct-drop: {cr:.1%}\n")

    if n < total:
        print(_yellow("Classify remaining items before applying gate."))
    elif fp >= 0.05:
        print(_red("GATE C") + " — FP-drop ≥5%. Verifier not safe. Close N9d.")
    elif fp <= 0.02 and cr >= 0.60:
        print(_green("GATE A") + " — Proceed:")
        print("  zkm scrub ner --with-verifier --apply")
    else:
        print(_yellow("GATE B") + " — Borderline. Review or adjust thresholds.")

    buckets: dict[str, int] = {}
    for r in rows:
        b = r.get("bucket", "").strip().lower()
        if b:
            buckets[b] = buckets.get(b, 0) + 1
    if buckets:
        print("\nBreakdown:")
        mx = max(buckets.values())
        for b, c in sorted(buckets.items(), key=lambda x: -x[1]):
            bar = "█" * int(c / mx * 24)
            print(f"  {b:20s}  {c:4d}  {bar}")

# ── Entry point ───────────────────────────────────────────────────────────────

def cmd_reset(args: argparse.Namespace) -> None:
    path = _resolve_tsv(args)
    if not path:
        sys.exit("No sample TSV found.")
    rows = _load_tsv(path)
    for r in rows:
        r["bucket"] = ""
    _save_tsv(path, rows)
    print(f"Reset {len(rows)} classifications in {path.name}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", default=None)
    p.add_argument("--pilot", default=None, help="Pilot JSONL (default: latest in store)")
    p.add_argument("--tsv",   default=None, help="Sample TSV (default: latest in store)")
    p.add_argument("--seed",  type=int, default=42)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--sample",   action="store_true", help="Generate 100-item sample TSV")
    mode.add_argument("--classify", action="store_true", help="Interactive classifier (default)")
    mode.add_argument("--gate",     action="store_true", help="Print Gate A/B/C result")
    mode.add_argument("--reset",    action="store_true", help="Clear all bucket classifications")
    args = p.parse_args()

    if args.sample:
        cmd_sample(args)
    elif args.gate:
        cmd_gate(args)
    elif args.reset:
        cmd_reset(args)
    else:
        cmd_classify(args)


if __name__ == "__main__":
    main()
