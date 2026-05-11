#!/usr/bin/env bash
# zkm-ner pilot — entity histogram + top-N + suspicious-value dump
# Reads from the live knowledge store; no extraction is run.
#
# Usage:
#   ./scripts/pilot.sh [--store PATH] [--top N] [--review PATH]
#
# Defaults:
#   --store   $ZKM_STORE or ~/knowledge
#   --top     20
#   --review  <store>/.zkm-state/ner-pilot-review-YYYYMMDD-HHMM.jsonl

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

# Prefer the plugin venv; fall back to whatever python3 is on PATH.
if [[ -x "$PLUGIN_DIR/.venv/bin/python" ]]; then
    PYTHON="$PLUGIN_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi

exec "$PYTHON" "$SCRIPT_DIR/pilot.py" "$@"
