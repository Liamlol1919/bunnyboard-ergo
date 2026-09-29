#!/usr/bin/env bash
# Routing-Pipeline fuer das Bunnyboard-Ergo. Reihenfolge:
#
#  1. ergo_transform.py   Positionen verschieben (loescht alte Tracks)
#  2. DSN export          ohne Tracks/Zonen
#  3. freerouting         headless (-de DSN -do SES -da)
#  4. SES import          in das Board ohne Tracks
#
# Das Board hat KEINE Zonenbeschichtung (Bunnyboard ist 2-lagig ohne Pour),
# deshalb entfaellt der Pour-Schritt der Lapwing-Pipeline.
#
# Aufruf: bash tools/route.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PCB="keyboard/kicad/bunnyboard_ergo.kicad_pcb"
SRC="keyboard/kicad/steno.kicad_pcb"
WORK="/tmp/ergo_route"
mkdir -p "$WORK"

echo "== 1/4 transform =="
rm -f "$PCB"
python3 tools/ergo_transform.py "$SRC" "$PCB" --verify 2>&1 \
    | grep -vE "memory leak|assert|PROPERTY|Debug:|duplicate"

echo "== 2/4 DSN export =="
python3 - "$PCB" "$WORK" <<'PY' 2>&1 | grep -vE "assert|PROPERTY|Debug:"
import pcbnew, sys
src, work = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(src)
for t in list(b.GetTracks()):
    b.Remove(t)
for z in list(b.Zones()):
    b.Remove(z)
clean = f"{work}/board_notracks.kicad_pcb"
pcbnew.SaveBoard(clean, b)
b2 = pcbnew.LoadBoard(clean)
pcbnew.ExportSpecctraDSN(b2, f"{work}/nav.dsn")
print("DSN ohne Tracks:", f"{work}/nav.dsn")
PY

echo "== 3/4 freerouting =="
java -jar "$HOME/.cache/lapwing/freerouting-2.2.4.jar" \
    -de "$WORK/nav.dsn" -do "$WORK/nav.ses" -da 2>&1 \
    | grep -E "session completed|unrouted" | tail -2

echo "== 4/4 SES import =="
python3 - "$WORK/board_notracks.kicad_pcb" "$WORK/nav.ses" "$PCB" <<'PY' 2>&1 | grep -vE "assert|PROPERTY|Debug:"
import pcbnew, sys
src, ses, dst = sys.argv[1], sys.argv[2], sys.argv[3]
b = pcbnew.LoadBoard(src)
pcbnew.ImportSpecctraSES(b, ses)
n = len([t for t in b.GetTracks()])
pcbnew.SaveBoard(dst, b)
print("Tracks+Vias nach SES:", n)
PY

echo "== DRC =="
kicad-cli pcb drc --severity-error -o "$WORK/drc.rpt" "$PCB" >/dev/null 2>&1 || true
grep -E "Found" "$WORK/drc.rpt" | tail -4
echo "Fertig: $PCB"
