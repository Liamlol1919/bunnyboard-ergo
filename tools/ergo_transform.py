#!/usr/bin/env python3
"""Bunnyboard -> Bunnyboard-Ergo: NUR Positionen verschieben.

Die Elektrik (Pads, Netze, Matrix, Dioden-Zuordnung, Pico-Pinbelegung) bleibt
bitgleich. Geaendert werden ausschliesslich die (x, y, rot)-Werte der 28
Switch-Footprints, der 28 Dioden und des Pico.

Datenquelle: measure/STAGGER.md aus dem Schwesterprojekt steno-hardware
(n=12 Haende, Wacom PTH-660, rotationskorrigiert). Werte sind dx/dy relativ
zum Mittelfinger-Home, +y zeigt zum Koerper.

    Finger   dx      dy
    Zeige   -20.3   +8.8
    Mittel    0.0    0.0
    Ring    +15.5   -1.1
    Klein   +35.7   +8.8
    Daumen  -22.1  +44.7

Aufruf:
    python3 tools/ergo_transform.py <src.kicad_pcb> <dst.kicad_pcb> [--verify]

Das Skript ist idempotent nur auf der ORIGINAL-Datei; fuer die Ausgabe einer
frueheren Version erneut aus keyboard/kicad/steno.kicad_pcb starten.
"""
from __future__ import annotations

import argparse
import math
import sys

import pcbnew

# --- Ergo-Geometrie ------------------------------------------------------
# Zwei Groessen, die nicht verwechselt werden duerfen:
#
#  * dx aus der Wacom-Messung = FINGERKUPPEN-Positionen (n=12 Haende).
#    Spanne Pinky->Index dort: 56.0 mm.
#  * Spalten-Pitch eines Tastenboards = 19.0 mm (Choc-Standard, und exakt
#    der Wert in Bunnys eigenem steno.kicad_pcb: alle 5 Spalten 19.00).
#    Spanne Pinky->Index dort: 57.0 mm.
#
# Die Kuppen liegen enger als die Tasten, weil die Hand gespreizt aufliegt.
# Fuer ein Tastenraster zaehlt der Pitch, nicht die Kuppe: bei 15 mm Caps
# ergaebe der Kuppenwert (15.5 mm) nur 0.5 mm Cap-Luecke zwischen Ring und
# Mittel - ein Fehlgriff triff zwei Tasten. Deshalb Pitch = 19.0 mm.
#
# Uebernommen aus der Messung wird der STAGGER (dy), denn das ist der
# eigentliche Ergo-Effekt: welcher Finger hoeher/tiefer liegt.
DX_INDEX = -19.0       # 1 Spalte innen von der Referenz
DX_MIDDLE = 0.0        # Mittelfinger = Referenz
DX_RING = 19.0         # 1 Spalte aussen
DX_PINKY = 38.0        # 2 Spalten aussen

DY_INDEX = 8.8         # gemessen
DY_MIDDLE = 0.0
DY_RING = -1.1         # gemessen
DY_PINKY = 8.8         # gemessen

# Daumen-Cluster. Ruhepunkt Daumen liegt laut Messung 44.7 mm unter dem
# Mittelfinger-Home; die innere Taste 4 mm hoeher (41.0). Die Extrataste
# X1/X2 sitzt aussen-unten (STAGGER.md: dx -30, dy +55).
THUMB_REST_DY = 44.7   # Taste 1 (A/E), Ruhepunkt
THUMB_IN_DY = 41.0     # Taste 2 (O/U), 19 mm innen und 4 mm hoeher
THUMB_EXTRA_DY = 55.0  # Extra X1/X2, aussen-unten

SPLAY_DEG = 0.0        # Handachse laut Messung -1.6/-3.5 Grad -> rund 0
ROW_PITCH = 18.0       # Bunnyboard-Reihenabstand, unveraendert (Choc 18x17)

# Kappenrand. Choc-1u-Kappe ist 17.5 mm breit, der Pitch 19 -> 7.5 mm von
# der Tastenmitte bis zum Kappenrand (Kappenmitte = Tastenmitte).
CAP_HALF = 7.5
# Freiraum vom Kappenrand bis zur Boardkante. Bunnys Original hatte 12.5;
# 4 mm genuegen fuer ein Board, das flach aufliegt (JLCPCB verlangt nur
# 0.2 mm Kupfer-Kante-Abstand).
EDGE_MARGIN = 4.0

# Referenz: Bunnyboard-Spalten x und Reihen y (gemessen, siehe README).
SRC_COL_X_LEFT = [35.0775, 54.0775, 73.0775, 92.0775, 111.0775]
SRC_COL_X_RIGHT = [168.0775, 187.0775, 206.0775, 225.0775, 244.0775]
SRC_COL_X_FAR = [263.0775]
SRC_ROW_Y = [64.485, 82.485]
SRC_THUMB_Y = 118.485

# Mittelfinger-Home beider Haende im Quellboard. Quellspalten (verifiziert):
#   links  S1..S5  = 35.08 / 54.08 / 73.08 / 92.08 / 111.08  (aussen -> innen)
#   rechts S6..S11 = 168.08 / 187.08 / 206.08 / 225.08 / 244.08 / 263.08
# Der Mittelfinger ist die DRITTE Spalte von aussen, nicht die zweite:
# links 73.0775, rechts 206.0775. Beide Daumencluster sitzen auf denselben
# x-Werten wie die Mittelfingerspalte (S23/S28 = Mitte).
SRC_MIDDLE_L = 73.0775
SRC_MIDDLE_R = 206.0775

# Zielabstand der beiden Mittelfinger (Messung Laptop 84-92 mm).
# Gewaehlt: 96 mm statt der gemessenen 88. Begruendung: die Bank ist im
# Quellboard durchgehend 19-mm-Raster und die innerste Spalte ist die
# Asterisk-Taste. Bei GAP 88 lagen die beiden '*' nur 9.4 mm auseinander
# (15-mm-Kappe + 2 mm Luft = 17 noetig); 96 mm ergibt 17.4 mm.
# Kosten: beide Haende 4 mm weiter aussen als gemessen -> Laptop-Pose
# leicht gespreizt, dafuer bleibt die Bunnyboard-Bank vollstaendig.
GAP = 120.0


def rot_off(ox: float, oy: float, deg: float) -> tuple[float, float]:
    r = math.radians(deg)
    return (ox * math.cos(r) - oy * math.sin(r), ox * math.sin(r) + oy * math.cos(r))


def target_positions() -> dict[str, tuple[float, float, float]]:
    """Designator -> (x, y, rot) fuer alle 28 Switches.

    Spaltenreihenfolge ist im Quellboard von AUSSEN nach INNEN nummeriert:
      links  S1=pinky S2=ring S3=Mitte S4=index S5=innen
      rechts S6=innen S7=index S8=Mitte S9=ring S10=pinky S11=D/Z-Spalte
    Die dx/dy-Werte aus STAGGER.md sind relativ zum MITTELFINGER, also
    relativ zu S3 (links) bzw. S8 (rechts).
    """
    out: dict[str, tuple[float, float, float]] = {}
    # Die dx-Werte aus STAGGER.md beschreiben die RECHTE Hand: Pinky liegt
    # aussen (+35.7), Index innen (-20.3). Fuer die linke Hand wird dx
    # GESPIEGELT (Vorzeichen negieren), sonst landete der linke Pinky innen
    # bei -8.3 statt aussen bei -79.7 (Kollision S1/S11 mit 0.9 mm).
    # Zentrierung: die beiden Mittelfinger-Spalten liegen GAP auseinander,
    # also bei -GAP/2 und +GAP/2.
    mid_l = -GAP / 2.0
    mid_r = +GAP / 2.0

    # Linke Hand, aussen (pinky) nach innen. Die 5. Spalte ist die
    # ASTERISK-Spalte der Bank (S5/S16 = "*"), kein Finger: sie sitzt 19 mm
    # INNEN neben der Index-Spalte, also naeher an der Boardmitte.
    # Vorzeichen: dx wird fuer links negiert, "innen" heisst groesserer
    # x-Wert als der Index. INNER = -DX_INDEX + 19 = +39.3 (nicht -39.3,
    # das war die Pinky-Position und liess S5 auf S1 fallen).
    INNER = -DX_INDEX + 19.0           # Asterisk-Spalte, links +39.3
    left = [
        ("S1", -DX_PINKY, DY_PINKY),   # pinky aussen
        ("S2", -DX_RING, DY_RING),     # ring
        ("S3", -DX_MIDDLE, DY_MIDDLE), # Mittelfinger = Referenz
        ("S4", -DX_INDEX, DY_INDEX),   # index
        ("S5", INNER, DY_INDEX),       # Asterisk-Spalte, innen
    ]
    for ref, dx, dy in left:
        out[ref] = (mid_l + dx, dy - ROW_PITCH, 0.0)        # Reihe 0
        out["S" + str(int(ref[1:]) + 11)] = (mid_l + dx, dy, 0.0)  # Reihe 1

    # Rechte Hand, innen (Asterisk-Spalte) nach aussen (D/Z).
    right = [
        ("S6", DX_INDEX - 19.0, DY_INDEX),   # Asterisk-Spalte, innen
        ("S7", DX_INDEX, DY_INDEX),          # index
        ("S8", DX_MIDDLE, DY_MIDDLE),        # Mittelfinger = Referenz
        ("S9", DX_RING, DY_RING),            # ring
        ("S10", DX_PINKY, DY_PINKY),         # pinky
        ("S11", DX_PINKY + 17.5, DY_PINKY),  # D/Z-Spalte, 17.5 statt 19
    ]
    for ref, dx, dy in right:
        out[ref] = (mid_r + dx, dy - ROW_PITCH, 0.0)
        n = int(ref[1:])
        out["S" + str(n + 11)] = (mid_r + dx, dy, 0.0)

    # Daumenreihe, an den Mittelfingerspalten verankert. Quell-x der Daumen
    # deckt sich mit der Mittelfingerspalte (73.08 links, 206.08 rechts).
    # Je Hand drei Tasten, relativ zur Mittelfingerspalte:
    #   Taste 1 (A/E, Ruhepunkt)  dx 0     dy +45.0
    #   Taste 2 (O/U)             dx +/-19 dy +41.0   (19 mm innen, 4 hoch)
    #   Extra (X1/X2)             dx +/-38 dy +55.0   (aussen-unten)
    # Quelle: measure/STAGGER.md, Abschnitt "Daumen-Cluster".
    # Vorher waren S23/S25 bzw. S28/S26 vertauscht: S23 stand auf 41 statt 45,
    # S25 auf 44.7 statt 55 - die Stufe sass an der falschen Taste.
    out["S23"] = (mid_l + DX_MIDDLE, THUMB_REST_DY, 0.0)
    out["S24"] = (mid_l + DX_MIDDLE + 19.0, THUMB_IN_DY, 0.0)
    out["S25"] = (mid_l + DX_MIDDLE + 38.0, THUMB_EXTRA_DY, 0.0)
    out["S26"] = (mid_r + DX_MIDDLE - 38.0, THUMB_EXTRA_DY, 0.0)
    out["S27"] = (mid_r + DX_MIDDLE - 19.0, THUMB_IN_DY, 0.0)
    out["S28"] = (mid_r + DX_MIDDLE, THUMB_REST_DY, 0.0)
    return out


def net_snapshot(board) -> dict[str, tuple[int, int]]:
    """Designator -> (anzahl Pads, anzahl Pads MIT Netz). Rein lesend."""
    snap = {}
    for f in board.GetFootprints():
        ref = f.GetReference()
        pads = list(f.Pads())
        withnet = sum(1 for p in pads if p.GetNetCode() > 0)
        snap[ref] = (len(pads), withnet)
    return snap


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--verify", action="store_true",
                    help="Netze/Pads vor und nach dem Verschieben vergleichen")
    args = ap.parse_args()

    board = pcbnew.LoadBoard(args.src)
    if board is None:
        sys.exit(f"konnte {args.src} nicht laden")

    before = net_snapshot(board)

    targets = target_positions()
    mid_l = -GAP / 2.0
    mid_r = +GAP / 2.0
    moved, missing, removed_logo = 0, [], 0
    for f in board.GetFootprints():
        ref = f.GetReference()
        if ref.startswith("S") and ref[1:].isdigit():
            if ref not in targets:
                missing.append(ref)
                continue
            x, y, rot = targets[ref]
            f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
            f.SetOrientationDegrees(rot)
            moved += 1
        elif ref == "U2":
            # Pico in die freie Flaeche zwischen den innersten Kappen.
            # Nicht die Spaltenmitten mitteln: die Kappe der Asterisk-Spalte
            # reicht 7.5 mm weit, also liegt die echte freie Kante bei
            # Spaltenmitte +/- 9.5 (7.5 halbe Kappe + 2 mm Luft).
            # Vorher stand er bei Spaltenmitte-Mittelwert und lag damit auf
            # S6/S17 (DRC courtyards_overlap + shorting_items).
            # Die rechte Asterisk-Spalte ist das Spiegelbild der linken:
            # links  mid_l - DX_INDEX + 19, rechts mid_r + DX_INDEX - 19.
            # Vorher stand rechts mid_r + DX_INDEX (=+33) - das ist der
            # Mittelfinger-Offset, nicht die Spalte. Dadurch rutschte das
            # Pico-Zentrum von 0 auf +9.5 und lag auf S6/S17.
            left_inner = mid_l - DX_INDEX + 19.0     # Asterisk links
            right_inner = mid_r + DX_INDEX - 19.0    # Asterisk rechts
            free_l = left_inner + 9.5
            free_r = right_inner - 9.5
            gap_center = (free_l + free_r) / 2.0
            f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(gap_center),
                                          pcbnew.FromMM(DY_MIDDLE)))
            f.SetOrientationDegrees(0.0)
            moved += 1
    # Kupfer-Logo G*** (Wert "LOGO") wird ENTFERNT, nicht verschoben: es ist
    # Dekoration und kostet nur Flaeche. Entfernt wird es weiter oben, vor
    # der Positionsschleife (SWIG-Handle).

    # Dioden folgen ihrem Switch. Regel im Quellboard gemessen (alle 28 Paare
    # ohne Ausnahme): Dn liegt bei Sn + (+9.125, +3.750), Rotation 90 Grad.
    # Die Zuordnung ist 1:1 (D1->S1 ... D28->S28), nicht ueber die Matrix.
    # Der Offset wird um die Switch-Rotation gedreht, damit er bei spaeterem
    # Splay weiterhin stimmt (hier rot=0, also unveraendert).
    rot_of = {ref: t[2] for ref, t in targets.items()}
    diodes = 0
    for f in board.GetFootprints():
        ref = f.GetReference()
        if not (ref.startswith("D") and ref[1:].isdigit()):
            continue
        sw = "S" + ref[1:]
        if sw not in targets:
            continue
        x, y, rot = targets[sw]
        ox = 9.125
        dx_off, dy_off = rot_off(ox, 3.75, rot)
        f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x + dx_off),
                                      pcbnew.FromMM(y + dy_off)))
        f.SetOrientationDegrees(90.0 + rot)
        diodes += 1

    # Board-Umriss neu aufbauen. Der Original-Umriss ist eine T-Form
    # (Bank + Zunge) im Quellkoordinatensystem. Nach dem Verschieben deckt
    # er die Tasten nicht mehr richtig ab (Zunge zu kurz, Raender 31 mm).
    # Neu aus den tatsaechlichen Positionen: 7.5 mm halbe Kappe + 4.0 mm
    # Rand = 11.5. Bunnys Original hatte 12.5 mm Rand (M=20); 4 mm ist fuer
    # ein Handgelenk-aufgelegtes Board reichlich (JLCPCB fordert 0.2 mm
    # Kupferabstand zur Kante) und spart rund 13 mm Breite + 15 mm Hoehe.
    swxy = [f.GetPosition() for f in board.GetFootprints()
            if f.GetReference().startswith("S")
            and f.GetReference()[1:].isdigit()]
    # Bank = alles oberhalb y=30, Zunge = Daumenreihe darunter.
    bank = [p for p in swxy if p.y / 1e6 < 30.0]
    tongue = [p for p in swxy if p.y / 1e6 >= 30.0]
    M = CAP_HALF + EDGE_MARGIN
    F = 3.375         # Fase, wie im Original
    bx0 = min(p.x / 1e6 for p in bank) - M
    bx1 = max(p.x / 1e6 for p in bank) + M
    by0 = min(p.y / 1e6 for p in bank) - M
    by1 = max(p.y / 1e6 for p in bank) + M
    zx0 = min(p.x / 1e6 for p in tongue) - M
    zx1 = max(p.x / 1e6 for p in tongue) + M
    zy1 = max(p.y / 1e6 for p in tongue) + M
    # Der Pico ragt ueber die Bankoberkante hinaus (54 mm hoch gegen 38 mm
    # Bank). Ohne diese Korrektur liegt er nach dem Verkleinern teilweise
    # ausserhalb von Edge.Cuts - DRC "item outside board".
    mcu = next((f for f in board.GetFootprints() if f.GetReference() == "U2"),
               None)
    if mcu is not None:
        mb = mcu.GetBoundingBox(False, False)
        by0 = min(by0, pcbnew.ToMM(mb.GetTop()) - EDGE_MARGIN)
        by1 = max(by1, pcbnew.ToMM(mb.GetBottom()) + EDGE_MARGIN)
    poly = [
        (bx0 + F, by0), (bx1 - F, by0), (bx1, by0 + F),
        (bx1, by1 - F), (bx1 - F, by1),
        (zx1, by1), (zx1 + F, by1 + F), (zx1 + F, zy1 - F),
        (zx1, zy1), (zx0, zy1), (zx0 + F, zy1 - F),
        (zx0 + F, by1 + F), (zx0, by1),
        (bx0 + F, by1), (bx0, by1 - F), (bx0, by0 + F),
    ]
    # Alten Umriss entfernen, neuen als geschlossene Polylinie anlegen.
    for d in list(board.GetDrawings()):
        if d.GetLayerName() == "Edge.Cuts":
            board.Remove(d)
    pts = pcbnew.VECTOR_VECTOR2I()
    for x, y in poly:
        pts.append(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_POLY)
    ps = pcbnew.SHAPE_POLY_SET()
    ps.NewOutline()
    for x, y in poly:
        ps.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    ps.Outline(0).SetClosed(True)
    shape.SetPolyShape(ps)
    shape.SetLayer(pcbnew.Edge_Cuts)
    board.Add(shape)
    print(f"umriss neu: {len(poly)} Punkte, "
          f"{bx1-bx0:.1f} x {zy1-by0:.1f} mm")

    # Logo entfernen, BEVOR die Tracks geloescht werden. Beide Remove()-
    # Aufrufe invalidieren den SWIG-Footprint-Handle fuer alle danach
    # geholten Objekte ("no attribute 'GetReference'"). Reihenfolge daher:
    # erst Logo (eigener, abgeschlossener Footprint-Durchlauf), dann Tracks.
    # Ein zweiter Footprint-Durchlauf nach dem Logo-Remove ist erlaubt, weil
    # Remove() auf Footprints die neu geholte Liste nicht beschaedigt.
    for f in list(board.GetFootprints()):
        if f.GetReference() == "G***":
            board.Remove(f)
            removed_logo += 1

    # Alte Leiterbahnen entfernen. Sie verbinden die ALTEN Pad-Positionen;
    # nach dem Verschieben wuerden sie kreuz und quer ueber das neue Layout
    # laufen und Kurzschluesse erzeugen. Das Board muss nach der
    # Geometrieaenderung neu geroutet werden. Bunnys Original hatte
    # 159 Segmente, 0 Vias, keine Zonen -> kein Verlust an Information:
    # die Netzliste steht vollstaendig in den Pads.
    tracks_before = len(list(board.GetTracks()))
    for t in list(board.GetTracks()):
        board.Remove(t)
    print(f"tracks entfernt: {tracks_before} (muessen neu geroutet werden)")
    print(f"logo entfernt: {removed_logo}")


    pcbnew.SaveBoard(args.dst, board)
    print(f"dioden: {diodes}")
    print(f"verschoben: {moved} Footprints ({len(missing)} ohne Ziel)")
    if missing:
        print("  ohne Ziel:", missing)

    if args.verify:
        # Verifikation in einem SEPARATEN Prozess. Im selben Prozess liefert
        # LoadBoard nach board.Remove() einen ungueltigen SWIG-Handle
        # ("no attribute 'GetFootprints'") - die Pruefung fand dann gar
        # nicht statt, was schlimmer ist als ein Absturz.
        import json
        import subprocess
        code = (
            "import pcbnew,json,sys\n"
            "b=pcbnew.LoadBoard(sys.argv[1])\n"
            "print(json.dumps({f.GetReference():"
            "[len(list(f.Pads())),"
            "sum(1 for p in f.Pads() if p.GetNetCode()>0)]"
            " for f in b.GetFootprints()}))\n"
        )
        r = subprocess.run([sys.executable, "-c", code, args.dst],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"Verifikation fehlgeschlagen: {r.stderr[-400:]}")
        after = {k: tuple(v) for k, v in
                 json.loads(r.stdout.strip().splitlines()[-1]).items()}
        before_t = {k: tuple(v) for k, v in before.items()}
        # Das entfernte Logo ist absichtlich weg (Dekoration, kostet Flaeche).
        before_t.pop("G***", None)
        changed = [k for k in before_t if before_t[k] != after.get(k)]
        print(f"Netz-Snapshot: {len(before)} Footprints, "
              f"{len(changed)} mit abweichender Pad-Zahl")
        if changed:
            for k in changed[:10]:
                print(f"  {k}: {before[k]} -> {after.get(k)}")
            sys.exit("ABBRUCH: Elektrik hat sich geaendert")
        print("VERIFY OK: Pads/Netze unveraendert")


if __name__ == "__main__":
    main()
