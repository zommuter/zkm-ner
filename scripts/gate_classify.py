#!/usr/bin/env python3
"""N9d Stage 2 gate — interactive batch classifier for verifier pilot verdicts.

## Usage

    # Step 1: produce the 100-item sample TSV (if not already done)
    uv run python scripts/gate_classify.py --sample

    # Step 2: classify interactively — single-key presses, no Enter needed
    uv run python scripts/gate_classify.py --classify

    # Step 3: compute Gate A/B/C from the completed file
    uv run python scripts/gate_classify.py --gate

## Keys  (question: "WHAT IS this entity?")

    1  real-entity     someone else's person/org/place          → keep
    2  my-own-info     your own name/email/phone                → drop (ubiquitous, low-signal)
    3  real-but-noisy  real name buried in footer/boilerplate   → keep
    4  junk            noise, artefact, common word             → drop

  Navigation:
    s  split   classify this batch item by item
    k  skip    defer to end
    q  quit    save and exit (resumes next time)

## Confusion matrix (verdict × bucket)

    verdict=DROP, bucket=1/3    →  FP  (verifier wrongly dropped a real entity)
    verdict=DROP, bucket=2/4    →  TP  (verifier correctly dropped own-info or junk)
    verdict=KEEP, bucket=1/3    →  TN  (verifier correctly kept a real entity)
    verdict=KEEP, bucket=2/4    →  FN  (verifier missed own-info or junk it should have dropped)

## Gate thresholds (docs/meeting-notes/2026-05-11-2316-n9d-llm-verifier-design.md)

    Gate A: FP-drop ≤2%  AND correct-drop ≥60%  →  zkm scrub ner --with-verifier --apply
    Gate B: FP-drop 2–5% OR  correct-drop <60%  →  iterate / adjust
    Gate C: FP-drop ≥5%                         →  close N9d, verifier not safe

  FP-drop = FP / (FP+TP)   — fraction of drops that hit a real entity
  correct-drop = TP / (FP+TP)  — fraction of drops that were actually junk
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
    "4": "junk",
    "s": "split",
    "k": "skip",
    "q": "quit",
}

LEGIT   = {"real-entity", "real-but-noisy"}
JUNK    = {"junk", "my-own-info"}
BUCKETS = LEGIT | JUNK

KEY_HINT = (
    " What IS this entity?  (→ what SHOULD happen to it)\n"
    "  [1] real-entity      someone else's person/org/place  → keep\n"
    "  [2] my-own-info      your own name/email/phone        → drop (ubiquitous)\n"
    "  [3] real-but-noisy   real name in footer/boilerplate  → keep\n"
    "  [4] junk             noise, artefact, common word     → drop\n"
    "  [s] split  [k] skip  [q] quit"
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
def _bg_red(s: str) -> str: return f"\033[41;97m{s}\033[0m"
def _bg_grn(s: str) -> str: return f"\033[42;97m{s}\033[0m"

# ── TSV helpers ───────────────────────────────────────────────────────────────

FIELDS = ["#", "verdict", "type", "value", "suspicious_reason", "context_snippet", "file", "bucket", "comment"]


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

    drops = [r for r in classified if r.get("verdict", "").strip().lower() == "drop"]
    keeps = [r for r in classified if r.get("verdict", "").strip().lower() == "keep"]

    fp = sum(1 for r in drops if r["bucket"].strip().lower() in LEGIT)
    tp = sum(1 for r in drops if r["bucket"].strip().lower() in JUNK)
    fn = sum(1 for r in keeps if r["bucket"].strip().lower() in JUNK)
    tn = sum(1 for r in keeps if r["bucket"].strip().lower() in LEGIT)

    n_drops = len(drops)
    n_keeps = len(keeps)
    return {
        "n": n, "n_drops": n_drops, "n_keeps": n_keeps,
        "fp": fp, "tp": tp, "fn": fn, "tn": tn,
        "fp_rate":      fp / n_drops if n_drops else 0.0,
        "correct_rate": tp / n_drops if n_drops else 0.0,
        "fn_rate":      fn / n_keeps if n_keeps else 0.0,
        "tn_rate":      tn / n_keeps if n_keeps else 0.0,
    }


def _print_gate(stats: dict, total: int) -> None:
    n  = stats["n"]
    fp = stats["fp_rate"]
    cr = stats["correct_rate"]
    done = _green(f"{n}/{total}") if n == total else _yellow(f"{n}/{total}")
    fp_s = _red(f"{fp:.1%}")   if fp  > 0.02 else _green(f"{fp:.1%}")
    cr_s = _green(f"{cr:.1%}") if cr  >= 0.60 else _yellow(f"{cr:.1%}")
    fn_s = _yellow(f"{stats['fn_rate']:.1%}") if stats["n_keeps"] else _dim("n/a")
    print(f"  {done} classified  |  DROP→FP: {fp_s}  correct: {cr_s}  |  KEEP→FN: {fn_s}")

# ── Batch grouping ────────────────────────────────────────────────────────────

def _group_batches(rows: list[dict], batch_size: int = 8) -> list[list[dict]]:
    unclassified = [r for r in rows if not r.get("bucket", "").strip()]
    # sort so items likely in the same bucket cluster: same reason, same type, same verdict
    unclassified.sort(key=lambda r: (
        r.get("suspicious_reason", ""),
        r.get("type", ""),
        r.get("verdict", ""),
    ))
    return [unclassified[i:i + batch_size] for i in range(0, len(unclassified), batch_size)]

# ── Display ───────────────────────────────────────────────────────────────────

def _fmt_value(v: str) -> str:
    v = v.replace("\n", "↵").replace("\r", "")
    if len(v) > 46:
        v = v[:43] + "…"
    return f"{v!r}"


def _verdict_tag(verdict: str) -> str:
    v = verdict.strip().lower()
    if v == "drop":
        return _bg_red(" DROP ")
    if v == "keep":
        return _bg_grn(" KEEP ")
    return _dim(f" {verdict[:4].upper()} ")


def _print_batch(batch: list[dict]) -> None:
    print()
    for row in batch:
        reason  = _dim(f"({row.get('suspicious_reason', '')})")
        ctx     = (row.get("context_snippet") or "").replace("\n", " ").strip()[:72]
        num     = _cyan(f"{row['#']:>3}.")
        vtag    = _verdict_tag(row.get("verdict", ""))
        print(f"  {num} {vtag} [{row['type']:6s}] {_fmt_value(row['value']):<46}  {reason}")
        if ctx:
            print(f"              {_dim(ctx)}")
    print()

# ── Recursive batch classifier (git add -p style) ────────────────────────────

def _classify_batch(
    batch: list[dict],
    by_num: dict,
    path: Path,
    rows: list[dict],
    total: int,
    skipped: list[dict],
    depth: int = 0,
) -> bool:
    """Classify a batch interactively. Returns False on quit, True otherwise.

    Split halves the batch recursively; at size 1 split is suppressed.
    """
    _print_batch(batch)
    n = len(batch)
    can_split = n > 1
    valid_keys = set(KEY_MAP) if can_split else (set(KEY_MAP) - {"s"})
    hint = KEY_HINT if can_split else KEY_HINT.replace("  [s] split  ", "  ")
    print(hint, flush=True)

    indent = "  " + "  " * depth
    label = f"{n} item{'s' if n > 1 else ''}"
    print(f"{indent}[{label}] > ", end="", flush=True)

    ch = _read_key(valid_keys)
    bucket = KEY_MAP[ch]
    print(ch)

    if bucket == "quit":
        return False

    if bucket == "skip":
        skipped.extend(r for r in batch if not r.get("bucket", "").strip())
        print(_dim(f"{indent}(skipped)"))
        return True

    if bucket == "split":
        mid = n // 2
        print(_dim(f"{indent}(split → {mid} + {n - mid})"))
        for sub in [batch[:mid], batch[mid:]]:
            if not _classify_batch(sub, by_num, path, rows, total, skipped, depth + 1):
                return False
            _save_tsv(path, rows)
        return True

    # bulk assign
    for row in batch:
        if not row.get("bucket", "").strip():
            by_num[row["#"]]["bucket"] = bucket
    print(f"{indent}{_green('✓')} {n} item{'s' if n > 1 else ''} → {_bold(bucket)}")

    # offer comment prompt only for single-item decisions
    if n == 1:
        row = batch[0]
        existing = row.get("comment", "").strip()
        prompt = f"{indent}note [{existing}]: " if existing else f"{indent}note (Enter to skip): "
        try:
            note = input(prompt).strip()
        except EOFError:
            note = ""
        if note:
            by_num[row["#"]]["comment"] = note
        elif existing:
            pass  # keep existing comment if nothing entered

    return True


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
        if not _classify_batch(batch, by_num, path, rows, total, skipped):
            _save_tsv(path, rows)
            print(_green("Saved. Resume: uv run python scripts/gate_classify.py --classify"))
            return
        stats = _gate_stats(rows)
        _print_gate(stats, total)
        _save_tsv(path, rows)

    # Deferred items — individually (can't split a single item)
    remaining = [r for r in skipped if not by_num[r["#"]].get("bucket", "").strip()]
    if remaining:
        print(_bold(f"\n── Deferred: {len(remaining)} items ──"))
        for row in remaining:
            if not _classify_batch([row], by_num, path, rows, total, [], depth=0):
                _save_tsv(path, rows)
                print(_green("Saved. Resume: uv run python scripts/gate_classify.py --classify"))
                return
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


def _stratified_sample(records: list[dict], target: int, seed: int) -> list[dict]:
    """Return up to `target` records stratified by (suspicious_reason, type)."""
    random.seed(seed)
    by_key: dict[tuple, list] = {}
    for r in records:
        key = (r.get("suspicious_reason") or "other", r.get("type") or "")
        by_key.setdefault(key, []).append(r)
    iters = {k: iter(random.sample(v, len(v))) for k, v in by_key.items()}
    keys = list(by_key.keys())
    sample: list = []
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
    return sample


def cmd_sample(args: argparse.Namespace) -> None:
    store = _resolve_store(args)
    pilot = Path(args.pilot) if getattr(args, "pilot", None) else _latest_pilot(store)
    if pilot is None:
        sys.exit("No pilot JSONL found. Run build_pilot_from_cache.py first.")

    records = [json.loads(l) for l in open(pilot, encoding="utf-8") if l.strip()]
    drops = [r for r in records if r.get("verdict") == "drop"]
    keeps = [r for r in records if r.get("verdict") == "keep"]

    if not drops:
        sys.exit("No 'drop' verdicts in pilot JSONL.")

    total_target = 100
    n_drops = min(60, len(drops))
    n_keeps = min(total_target - n_drops, len(keeps))

    seed = getattr(args, "seed", 42)
    sample_drops = _stratified_sample(drops, n_drops, seed)
    sample_keeps = _stratified_sample(keeps, n_keeps, seed + 1)
    sample = sample_drops + sample_keeps
    random.seed(seed + 2)
    random.shuffle(sample)

    out = pilot.with_name(pilot.stem + "-sample.tsv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        for i, r in enumerate(sample, 1):
            writer.writerow({
                "#": i,
                "verdict": r.get("verdict", ""),
                "type": r.get("type", ""),
                "value": r.get("value", ""),
                "suspicious_reason": r.get("suspicious_reason", ""),
                "context_snippet": (r.get("context_snippet") or "").replace("\n", " ")[:120],
                "file": r.get("file", ""),
                "bucket": "",
                "comment": "",
            })

    print(f"Sample: {len(sample_drops)} DROP + {len(sample_keeps)} KEEP = {len(sample)} items → {out}")
    print(f"Next: uv run python scripts/gate_classify.py --classify")

# ── Gate report ───────────────────────────────────────────────────────────────

def cmd_gate(args: argparse.Namespace) -> None:
    path = _resolve_tsv(args)
    if not path:
        sys.exit("No sample TSV found.")
    rows = _load_tsv(path)
    stats = _gate_stats(rows)
    n = stats["n"]
    total = len(rows)

    unclassified = total - n
    if unclassified:
        print(_yellow(f"Warning: {unclassified}/{total} items unclassified."), file=sys.stderr)

    fp, tp, fn, tn = stats["fp"], stats["tp"], stats["fn"], stats["tn"]
    fpr = stats["fp_rate"]
    cr  = stats["correct_rate"]
    fnr = stats["fn_rate"]

    print(f"\n{'':4}{'DROP verdict':>14}  {'KEEP verdict':>14}")
    print(f"  {'real entity':12}  {_red(f'FP={fp}'):>20}  {_green(f'TN={tn}'):>20}")
    print(f"  {'junk':12}  {_green(f'TP={tp}'):>20}  {_yellow(f'FN={fn}'):>20}")
    print()
    print(f"  DROP subset ({stats['n_drops']} classified):  FP-drop={fpr:.1%}  correct-drop={cr:.1%}")
    print(f"  KEEP subset ({stats['n_keeps']} classified):  FN-keep={fnr:.1%}  TN-keep={stats['tn_rate']:.1%}")
    print()

    if n < total:
        print(_yellow("Classify remaining items before applying gate."))
    elif fpr >= 0.05:
        print(_red("GATE C") + " — FP-drop ≥5%. Verifier not safe. Close N9d.")
    elif fpr <= 0.02 and cr >= 0.60:
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

# ── Reset ─────────────────────────────────────────────────────────────────────

def cmd_reset(args: argparse.Namespace) -> None:
    path = _resolve_tsv(args)
    if not path:
        sys.exit("No sample TSV found.")
    rows = _load_tsv(path)
    for r in rows:
        r["bucket"] = ""
    _save_tsv(path, rows)
    print(f"Reset {len(rows)} classifications in {path.name}")

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", default=None)
    p.add_argument("--pilot", default=None, help="Pilot JSONL (default: latest in store)")
    p.add_argument("--tsv",   default=None, help="Sample TSV (default: latest in store)")
    p.add_argument("--seed",  type=int, default=42)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--sample",   action="store_true", help="Generate 100-item sample TSV (60 DROP + 40 KEEP)")
    mode.add_argument("--classify", action="store_true", help="Interactive classifier (default)")
    mode.add_argument("--gate",     action="store_true", help="Print Gate A/B/C result with confusion matrix")
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
