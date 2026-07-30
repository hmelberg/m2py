#!/bin/sh
# Diff hjelpesidenes fellesseksjoner mot søskenrepoene.
#
# Lag 2 (verktøy) og lag 3 (referanse) skal være byte-identiske i safestat,
# openstat, askstat og microdata. Lag 0 (hero), modustabellen og lag 1
# (kjernen) er repo-spesifikke og med vilje utenfor sjekken.
#
# Exit 1 ved avvik. Søsken som ikke er sjekket ut lokalt hoppes over, det
# samme gjelder filer/søsken som ennå ikke har noen SYNC-blokker i det hele
# tatt (Task 9/11/13/15 ruller dette ut gradvis) og enkeltblokker som ikke
# finnes hos NOEN av de to sidene ennå. Det som faktisk feiler er en blokk
# som finnes på begge sider MED ulikt innhold — det er driften vi jakter på.
#
# HJELP_SYNC_ROOT og HJELP_SYNC_SIBLINGS kan overstyres — testen bruker det for
# å bygge et falskt søsken med en sabotert blokk og bekrefte at exit 1 faktisk
# inntreffer. Uten overstyring er standarden søskenrepoene ved siden av dette.
#
# HJELP_SYNC_STRICT=1 slår av ALL toleranse — også på blokknivå: hvert
# "hopper over" (fil mangler lokalt, fil mangler hos søsken, fil har ingen
# SYNC-blokker i det hele tatt, ELLER én bestemt blokk mangler hos begge
# sider) blir en feil i stedet for et hopp, med en melding om hva som
# manglet. Uten dette kunne en fil — eller én enkelt blokk — miste hele
# synk-innføringen stille (f.eks. en kopi som bommer på hjelp.en.html, eller
# en blokk som blir glemt i alle repoer under Task 9/11/13/15) og likevel gi
# exit 0. Task 17 kjører med HJELP_SYNC_STRICT=1 som sluttport fra alle fire
# repoer og krever null hopp av noe slag. Standard er ulåst (STRICT=0) — det
# er riktig under selve utrullingen (Task 4-15).
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOT="${HJELP_SYNC_ROOT:-$HERE/..}"
SIBLINGS="${HJELP_SYNC_SIBLINGS:-openstat askstat microdata}"
STRICT="${HJELP_SYNC_STRICT:-0}"
BLOCKS="felles-css felles-js felles-running felles-editor felles-sidebar
        felles-lagre felles-forklar felles-widgets felles-ai felles-eksempler
        felles-referanse-snarveier felles-referanse-tab"
FILES="hjelp.html hjelp.en.html"

fail=0
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Hent én SYNC-blokk ut av en fil. Godtar /* */ og <!-- -->.
extract() {
  awk -v name="$2" '
    $0 ~ ("SYNC:START[ \t]+" name "([ \t]*\\*/|[ \t]*-->)") { on=1; next }
    on && /SYNC:END/ { on=0 }
    on { print }
  ' "$1"
}

# Hopp over noe som ikke kan sjekkes ennå (ikke sjekket ut / ingen
# SYNC-blokker). I HJELP_SYNC_STRICT=1 er ethvert hopp en feil.
skip() {
  if [ "$STRICT" = "1" ]; then
    echo "STRENGT: $1 (HJELP_SYNC_STRICT=1 tillater ingen hopp-over)" >&2
    fail=1
  else
    echo "hopper over $1"
  fi
}

for f in $FILES; do
  if [ ! -f "$HERE/$f" ]; then
    skip "$f (finnes ikke her)"
    continue
  fi
  if ! grep -q "SYNC:START" "$HERE/$f"; then
    skip "$f (ingen SYNC-blokker her ennå)"
    continue
  fi
  for sib in $SIBLINGS; do
    sibfile="$ROOT/$sib/$f"
    if [ ! -f "$sibfile" ]; then
      skip "$sib/$f (ikke sjekket ut)"
      continue
    fi
    if ! grep -q "SYNC:START" "$sibfile"; then
      skip "$sib/$f (ingen SYNC-blokker der ennå)"
      continue
    fi
    for b in $BLOCKS; do
      extract "$HERE/$f" "$b" > "$tmp/a"
      extract "$sibfile" "$b" > "$tmp/b"
      if [ ! -s "$tmp/a" ] && [ ! -s "$tmp/b" ]; then
        skip "blokk '$b' i $f (mangler i både safestat og $sib)"
        continue
      fi
      if [ ! -s "$tmp/a" ]; then
        echo "AVVIK: blokk '$b' mangler i safestat/$f" >&2
        fail=1
        continue
      fi
      if [ ! -s "$tmp/b" ]; then
        echo "AVVIK: blokk '$b' mangler i $sib/$f" >&2
        fail=1
        continue
      fi
      if ! diff -q "$tmp/a" "$tmp/b" >/dev/null; then
        echo "AVVIK i $f, blokk '$b': safestat vs $sib" >&2
        diff -u "$tmp/a" "$tmp/b" | head -40 >&2
        fail=1
      fi
    done
  done
done

if [ "$fail" -ne 0 ]; then
  echo "" >&2
  echo "Fellesseksjonene har drevet fra hverandre. safestat er kanonisk —" >&2
  echo "kopier derfra til søskenet, ikke omvendt." >&2
  exit 1
fi

echo "hjelp_sync_check: fellesseksjonene stemmer"
