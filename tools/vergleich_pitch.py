#!/usr/bin/env python3
"""Vergleichsrender: Kuppenmass vs 19-mm-Tastenraster."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

DY = {"index": 8.8, "middle": 0.0, "ring": -1.1, "pinky": 8.8}
ROW = 18.0
# 120 mm statt der gemessenen 84-92: der Pico-Sockel (23.1 mm breit) sitzt
# zwischen den Asterisk-Spalten und braucht 2x9.125 mm Dioden-Offset plus
# Luft -> 42.1 mm Asterisk-Abstand. Bei GAP 96 ist das nicht darstellbar.
GAP = 120.0
SW = 15.0

VARIANTS = [
    ("V1 Kuppenmass (Wacom dx)",
     {"index": -20.3, "middle": 0.0, "ring": 15.5, "pinky": 35.7}),
    ("V2 19-mm-Tastenraster",
     {"index": -19.0, "middle": 0.0, "ring": 19.0, "pinky": 38.0}),
]

fig, axes = plt.subplots(2, 1, figsize=(14, 9))
for ax, (title, DX) in zip(axes, VARIANTS):
    keys = []
    for sign, side in ((-1, "L"), (1, "R")):
        mx = sign * GAP / 2
        for f in ("pinky", "ring", "middle", "index"):
            # links spiegeln
            dx = -DX[f] if sign < 0 else DX[f]
            keys.append((mx + dx, DY[f] - ROW, f, side))
            keys.append((mx + dx, DY[f], f, side))
        inner = sign * GAP / 2 + (abs(DX["index"]) + 19) * sign
        keys.append((inner, DY["index"] - ROW, "*", side))
        keys.append((inner, DY["index"], "*", side))
    for t in range(3):
        keys.append((-48 + t * 19, 41 + (4 if t == 2 else 0), "T", "L"))
        keys.append((48 - t * 19, 41 + (4 if t == 2 else 0), "T", "R"))
    for x, y, lab, side in keys:
        col = "tab:blue" if side == "L" else "tab:red"
        ax.add_patch(Rectangle((x - SW / 2, y - SW / 2), SW, SW,
                               fc=col, ec="black", alpha=0.7))
        ax.text(x, y, lab, ha="center", va="center", fontsize=7,
                color="white", fontweight="bold")
    xs = [k[0] for k in keys]
    ax.set_xlim(min(xs) - 20, max(xs) + 20)
    ax.set_ylim(60, -35)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.25)
    ax.set_title(title + "  -  Cap-Luecke Ring/Mittel: "
                 + f"{round((DX['ring'] - DX['middle']) - SW, 1)} mm")
fig.tight_layout()
fig.savefig("vergleich_pitch.png", dpi=110)
print("OK vergleich_pitch.png")
