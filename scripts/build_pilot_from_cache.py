#!/usr/bin/env python3
"""Build a pilot JSONL from already-cached verifier verdicts — no LLM calls.

Re-walks md files, checks is_suspicious(), looks up each entity in
ExtractionCache. Emits one JSONL record per cache hit. Safe to run
in parallel with a live scrub (read-only).

Usage:
    uv run python scripts/build_pilot_from_cache.py [--store PATH] [--out PATH] [--model MODEL]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_plugin_root = Path(__file__).parent.parent
sys.path.insert(0, str(_plugin_root / "src"))
_venv_site = list((_plugin_root / ".venv").glob("lib/python*/site-packages"))
if _venv_site:
    sys.path.insert(0, str(_venv_site[0]))

# Also need zkm core on path
_zkm_src = _plugin_root.parent.parent / "src"
if _zkm_src.exists():
    sys.path.insert(0, str(_zkm_src))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=None, help="Store path (default: $ZKM_STORE or ~/knowledge)")
    parser.add_argument("--out", default=None, help="Output JSONL path (default: <store>/.zkm-state/ner-verifier-pilot-cached-<ts>.jsonl)")
    parser.add_argument("--model", default="aya-expanse-8b", help="Verifier model name (default: aya-expanse-8b)")
    args = parser.parse_args()

    import os
    from datetime import datetime

    store = Path(args.store) if args.store else Path(os.environ.get("ZKM_STORE", Path.home() / "knowledge"))
    if not store.exists():
        sys.exit(f"Store not found: {store}")

    ts = datetime.now().strftime("%Y%m%d-%H%M")
    out_path = Path(args.out) if args.out else store / ".zkm-state" / f"ner-verifier-pilot-cached-{ts}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    from zkm.extraction_cache import ExtractionCache
    from zkm_ner.suspicious import is_suspicious
    from zkm_ner.verifier import _MODEL_VERSION_SUFFIX

    cache = ExtractionCache(store, extractor_name="ner_verifier")
    model_version = _MODEL_VERSION_SUFFIX
    model = args.model

    import frontmatter

    md_files = sorted(
        p for p in store.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(store).parts[:-1])
    )

    records = 0
    files_checked = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for md_path in md_files:
            try:
                post = frontmatter.load(str(md_path))
            except Exception:
                continue
            entities = post.metadata.get("entities")
            if not entities:
                continue
            files_checked += 1
            context_snippet = post.content[:200]
            for e in entities:
                if not isinstance(e, dict):
                    continue
                value = e.get("value", "")
                etype = e.get("type", "")
                reason = is_suspicious(etype, value)
                if not reason:
                    continue
                # Replicate verifier cache key: sha256(f"{value}:{type}")
                body_sha256 = hashlib.sha256(f"{value}:{etype}".encode()).hexdigest()
                cached = cache.get(body_sha256, model_name=model, model_version=model_version)
                if cached is None:
                    continue
                verdict = cached[0] if cached else "unclear"
                rec = {
                    "value": value,
                    "type": etype,
                    "verdict": verdict,
                    "suspicious_reason": reason,
                    "file": str(md_path.relative_to(store)),
                    "context_snippet": context_snippet,
                    "is_control": False,
                }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                records += 1

    print(f"Checked {files_checked} files with entities; {records} cache-hit records written to {out_path}")


if __name__ == "__main__":
    main()
