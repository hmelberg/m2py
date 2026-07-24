#!/bin/sh
# sync_check.sh — diff delte kjernefiler mot søsken-repoen microdata.
# Kjøres fra safestat-roten (kanonisk repo: motor-fikser lander her først
# og portes ut). Lister filer som avviker; exit 1 hvis noen gjør det.
# UI-filer (index.html, js/) er BEVISST utelatt — de drifter fritt.
#
# openstat-benet er FJERNET 2026-07-24 (scope B, se openstats
# docs/PLAN_remove_engine.md): openstat har ikke lenger motoren
# (m2py m.fl. slettet) og er en selvstendig kodebase. Delingen er nå
# safestat <-> microdata.
#
#   sh scripts/sync_check.sh            # sjekk microdata
#   sh scripts/sync_check.sh microdata  # eksplisitt

set -u
here="$(cd "$(dirname "$0")/.." && pwd)"
siblings="${1:-microdata}"

# Delte kjernefiler/-kataloger (motor + metadata). Hold listen i sync med
# README-avsnittet om søsken-repoene.
# (py2m/r2m er fjernet fra openstat/safestat 2026-07-10 — de eies nå av
# microdata-repoen alene og skal ikke synces.)
core="
m2py.py
functions.py
protect.py
m2py_translate.py
mockdata_core.py
mockdata_export.py
mockdata_realism.py
static_source.py
command_help.js
variable_metadata.json
codelists
"

status=0
for sib in $siblings; do
  sibdir="$here/../$sib"
  if [ ! -d "$sibdir" ]; then
    echo "MANGLER: $sibdir (klon søsken-repoen ved siden av safestat)"
    status=1
    continue
  fi
  echo "== safestat vs $sib =="
  for f in $core; do
    if [ ! -e "$here/$f" ] && [ ! -e "$sibdir/$f" ]; then
      continue  # finnes i ingen av dem (f.eks. mockdata_* i en trimmet build)
    fi
    if [ ! -e "$sibdir/$f" ]; then
      echo "  BARE I SAFESTAT: $f"
      status=1
    elif [ ! -e "$here/$f" ]; then
      echo "  BARE I $sib: $f"
      status=1
    elif ! diff -rq -x '__pycache__' -x '*.pyc' "$here/$f" "$sibdir/$f" >/dev/null 2>&1; then
      echo "  AVVIK: $f"
      diff -rq -x '__pycache__' -x '*.pyc' "$here/$f" "$sibdir/$f" 2>/dev/null | sed 's/^/    /' | head -10
      status=1
    fi
  done
done
[ $status -eq 0 ] && echo "OK: alle kjernefiler er i sync."
exit $status
