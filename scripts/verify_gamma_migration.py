"""γ schema migration verifier — hard gate for v1.x release.

Compares stored entity frontmatter (graceful-read) against a fresh extraction
on a corpus sample.  Exits non-zero on:

  - γ-collision: duplicate (scope, type, value) in any document's frontmatter
  - schema errors: entities missing required 'type' or 'value' fields

Agreement rate (stored == fresh) is printed but NOT gated — pipeline drift
from scrub passes and model-version bumps is expected and normal.

Usage:
    python verify_gamma_migration.py [--store PATH] [--sample N] [--seed INT]
                                     [--out PATH] [--full-corpus]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path setup — must precede any zkm_ner import
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR.parent / "src"))
_venv_site = list((_SCRIPT_DIR.parent / ".venv").glob("lib/python*/site-packages"))
if _venv_site:
    sys.path.insert(0, str(_venv_site[0]))


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _ent_scope(e: dict) -> str:
    """Graceful-read: missing scope treated as 'body' (pre-γ entries)."""
    return e.get("scope", "body")


def _ent_key(e: dict) -> tuple[str, str, str]:
    return (_ent_scope(e), e["type"], e["value"])



def _extract_fresh(body: str, lang: str | None = None) -> list[dict]:
    """Re-extract entities from *body* using current pipeline (cache bypassed)."""
    from zkm_ner.extract import extract
    try:
        return [e.as_dict() for e in extract(body, lang=lang)]
    except Exception as ex:
        print(f"WARNING: extraction failed: {ex}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Core verification logic
# ---------------------------------------------------------------------------


def verify(
    store: Path,
    *,
    sample_size: int,
    seed: int,
    full_corpus: bool,
    out_path: Path,
) -> dict:
    """Run verification and return stats dict.  Does not call sys.exit."""
    import frontmatter as _fm

    print("Scanning md files...", file=sys.stderr)
    all_md = [
        p for p in sorted(store.rglob("*.md"))
        if not any(part.startswith(".") for part in p.relative_to(store).parts[:-1])
    ]

    enriched: list[Path] = []
    for p in all_md:
        try:
            import frontmatter as _fm_scan
            post_scan = _fm_scan.load(str(p))
            raw_scan = post_scan.metadata.get("entities")
            if raw_scan:  # any non-empty entities list, even malformed
                enriched.append(p)
        except Exception:
            pass

    print(f"  {len(all_md)} total md files, {len(enriched)} have entities", file=sys.stderr)

    sample = enriched if full_corpus else random.Random(seed).sample(
        enriched, min(sample_size, len(enriched))
    )
    n = len(sample)
    print(f"  Sampling {n} files (seed={seed}{'  [full corpus]' if full_corpus else ''})", file=sys.stderr)

    agreement = 0
    pre_gamma_files = 0
    pre_gamma_entities_total = 0
    schema_error_files = 0
    collision_files = 0
    only_in_stored_total = 0
    only_in_fresh_total = 0
    diff_records: list[dict] = []

    for idx, md_path in enumerate(sample, 1):
        if idx % 50 == 0:
            print(f"  {idx}/{n} ...", file=sys.stderr)

        try:
            post = _fm.load(str(md_path))
        except Exception:
            continue

        raw_entities: list = post.metadata.get("entities") or []
        if not isinstance(raw_entities, list):
            continue

        # Schema integrity: entities must have type + value
        if any(not (isinstance(e, dict) and "type" in e and "value" in e) for e in raw_entities):
            schema_error_files += 1

        stored = [e for e in raw_entities if isinstance(e, dict) and "type" in e and "value" in e]

        # Pre-γ detection: stored entries missing the 'scope' field
        pre_gamma_count = sum(1 for e in stored if "scope" not in e)
        if pre_gamma_count:
            pre_gamma_files += 1
            pre_gamma_entities_total += pre_gamma_count

        # γ-collision: duplicate (scope, type, value) after graceful-read
        stored_keys_list = [_ent_key(e) for e in stored]
        if len(stored_keys_list) != len(set(stored_keys_list)):
            collision_files += 1

        stored_key_set = set(stored_keys_list)

        lang = post.metadata.get("lang") or None
        fresh = _extract_fresh(post.content, lang=lang)
        fresh_key_set = {_ent_key(e) for e in fresh}

        only_stored = stored_key_set - fresh_key_set
        only_fresh = fresh_key_set - stored_key_set
        only_in_stored_total += len(only_stored)
        only_in_fresh_total += len(only_fresh)

        if stored_key_set == fresh_key_set:
            agreement += 1
        else:
            diff_records.append({
                "file": str(md_path.relative_to(store)),
                "stored": len(stored_key_set),
                "fresh": len(fresh_key_set),
                "pre_gamma_in_file": pre_gamma_count,
                "only_in_stored": [list(k) for k in sorted(only_stored)[:20]],
                "only_in_fresh": [list(k) for k in sorted(only_fresh)[:20]],
            })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        for rec in diff_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return {
        "n": n,
        "agreement": agreement,
        "agreement_rate": agreement / n if n else 0.0,
        "pre_gamma_files": pre_gamma_files,
        "pre_gamma_entities": pre_gamma_entities_total,
        "schema_error_files": schema_error_files,
        "collision_files": collision_files,
        "only_in_stored": only_in_stored_total,
        "only_in_fresh": only_in_fresh_total,
        "diff_written": len(diff_records),
        "diff_path": str(out_path),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="γ schema migration verifier (E5)")
    parser.add_argument("--store", default="", help="Store path (default: $ZKM_STORE or ~/knowledge)")
    parser.add_argument("--sample", type=int, default=200, help="Files to sample (default: 200)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--out", default="", help="JSONL output path for per-file diffs")
    parser.add_argument("--full-corpus", action="store_true", help="Verify all enriched files (slow)")
    args = parser.parse_args(argv)

    store_str = args.store or os.environ.get("ZKM_STORE", "") or str(Path.home() / "knowledge")
    store = Path(store_str).expanduser().resolve()
    if not store.exists():
        print(f"ERROR: store not found: {store}", file=sys.stderr)
        sys.exit(1)

    out_path = (
        Path(args.out) if args.out
        else store / ".zkm-state" / "verify-gamma-migration.jsonl"
    )

    stats = verify(store, sample_size=args.sample, seed=args.seed,
                   full_corpus=args.full_corpus, out_path=out_path)

    n = stats["n"]
    print()
    print(f"=== γ migration verification — {n} files ===")
    print(f"  Agreement (stored == fresh):     {stats['agreement']}/{n}  ({stats['agreement_rate']:.1%})  [informational]")
    print(f"  Pre-γ files (no scope field):    {stats['pre_gamma_files']}  ({stats['pre_gamma_entities']} entities)")
    print(f"  γ-collision files:               {stats['collision_files']}  [GATE — must be 0]")
    print(f"  Schema-error files:              {stats['schema_error_files']}  [GATE — must be 0]")
    print(f"  Only in stored (pipeline drift): {stats['only_in_stored']}")
    print(f"  Only in fresh  (would be added): {stats['only_in_fresh']}")
    print(f"  Diff JSONL:                      {stats['diff_path']}")

    ok = stats["collision_files"] == 0 and stats["schema_error_files"] == 0

    if ok:
        print(f"\nPASS: γ migration is clean (no collisions, no schema errors)")
    else:
        failures = []
        if stats["collision_files"] > 0:
            failures.append(f"{stats['collision_files']} γ-collision file(s)")
        if stats["schema_error_files"] > 0:
            failures.append(f"{stats['schema_error_files']} schema-error file(s)")
        print(f"\nFAIL: {'; '.join(failures)}", file=sys.stderr)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
