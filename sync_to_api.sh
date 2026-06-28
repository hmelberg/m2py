#!/usr/bin/env bash
#
# Sync the canonical m2py engine into the microdata-api (Anvil) app.
#
# m2py.py and functions.py are the SOURCE OF TRUTH in this repo. The copies in
# microdata-api/server_code/ are GENERATED — the Anvil server imports them via
# m2py_shim.py to validate scripts (deep_validate). Edit the engine HERE, then
# run this script to propagate it; never edit the API copies directly.
#
# Usage:
#   ./sync_to_api.sh [API_DIR]          # copy engine -> API (default ../microdata-api)
#   ./sync_to_api.sh --check [API_DIR]  # verify in sync; exit 1 if not (for CI)
#
# API_DIR may also be set via the MICRODATA_API_DIR env var.
#
# Note on disclosure control: the synced engine defaults disclosure control OFF.
# That is correct for the validator, whose dry-run uses a tiny synthetic frame
# (200 rows) — with disclosure ON the population rules (T1>=1000, etc.) would
# falsely reject valid scripts. The validator catches syntax/runtime errors, not
# disclosure compliance (which can't be judged on a 200-row synthetic frame).
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CHECK=0
if [ "${1:-}" = "--check" ]; then CHECK=1; shift; fi
API_DIR="${1:-${MICRODATA_API_DIR:-$SRC_DIR/../microdata-api}}"
DEST="$API_DIR/server_code"

if [ ! -d "$DEST" ]; then
  echo "ERROR: $DEST not found. Pass API_DIR or set MICRODATA_API_DIR." >&2
  exit 2
fi

FILES=(m2py.py functions.py)

HEADER="$(mktemp)"
trap 'rm -f "$HEADER"' EXIT
cat > "$HEADER" <<'EOF'
# ============================================================================
# GENERATED COPY — DO NOT EDIT HERE.
# Source of truth: the m2py repo (m2py.py / functions.py). This file is produced
# by sync_to_api.sh. Edit the engine in the m2py repo and re-run that script;
# direct edits here are overwritten on the next sync.
# ============================================================================
EOF

status=0
for f in "${FILES[@]}"; do
  desired="$(mktemp)"
  cat "$HEADER" "$SRC_DIR/$f" > "$desired"
  if [ "$CHECK" = "1" ]; then
    if diff -q "$desired" "$DEST/$f" >/dev/null 2>&1; then
      echo "ok:  $f"
    else
      echo "OUT OF SYNC: $f  (run ./sync_to_api.sh to fix)"
      status=1
    fi
  else
    cp "$desired" "$DEST/$f"
    echo "synced: $f -> $DEST/$f"
  fi
  rm -f "$desired"
done

if [ "$CHECK" = "1" ] && [ "$status" -eq 0 ]; then
  echo "API engine copies are in sync."
fi
exit $status
