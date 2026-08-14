"""NPR tiles with alien crystal / seed-pod marks (art-bible §2 / §3.6).

Not brick, shingle, or wood grain. Graphic facets, crescent growth ridges,
and sparse signal-orchid / tide-teal veins.
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "textures"))

CORAL = (216, 102, 91)
CORAL_DK = (138, 62, 72)
PLUM = (90, 63, 88)
CREAM = (231, 210, 163)
CREAM_DK = (184, 158, 110)
BASALT = (75, 82, 104)
INK = (23, 36, 59)
MINT = (120, 201, 164)
TEAL = (47, 140, 135)
ORCHID = (154, 106, 203)
AMBER = (242, 168, 91)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def save(img, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    img.save(path)
    print("NPR_TILE", path, img.size)


def _facet_poly(cx, cy, r, n, rot):
    pts = []
    for i in range(n):
        a = rot + i * math.tau / n
        rr = r * (0.72 if i % 2 else 1.0)
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return pts


def paint_shell_variant(name, base, dark, accent, vein, motif, size=1024):
    img = Image.new("RGB", (size, size), base)
    draw = ImageDraw.Draw(img)
    if motif == "facet":
        seeds = [
            (180, 200, 150, 6, 0.2), (620, 280, 170, 7, 0.35),
            (400, 620, 190, 5, 0.1), (820, 720, 140, 6, 0.5),
            (220, 820, 160, 8, 0.0), (700, 920, 130, 5, 0.4),
            (80, 480, 110, 6, 0.7), (940, 180, 100, 7, 0.15),
        ]
        for cx, cy, r, n, rot in seeds:
            draw.polygon(_facet_poly(cx, cy, r, n, rot), fill=lerp(base, dark, 0.35))
            draw.polygon(_facet_poly(cx, cy, r * 0.55, max(3, n - 2), rot + 0.3), fill=lerp(base, accent, 0.22))
        for box, w in (((80, 120, 500, 280), 10), ((480, 540, 980, 700), 8), ((40, 740, 420, 900), 9)):
            draw.arc(box, 200, 340, fill=dark, width=w)
    elif motif == "hex":
        step = 92
        for row, y in enumerate(range(40, size, step)):
            ox = (step // 2) if row % 2 else 0
            for x in range(-40, size, step):
                draw.polygon(_facet_poly(x + ox, y, 38, 6, 0.0), outline=dark, width=3)
                if (x + y) % 3 == 0:
                    draw.polygon(_facet_poly(x + ox, y, 16, 5, 0.4), fill=accent)
        for x0, y0, x1, y1 in ((80, 60, 300, 400), (600, 200, 900, 700), (200, 700, 500, 980)):
            draw.line((x0, y0, x1, y1), fill=vein, width=4)
    elif motif == "pod":
        for cx, cy, r in ((220, 220, 110), (720, 260, 90), (480, 620, 140), (180, 820, 80), (840, 780, 100)):
            draw.ellipse((cx - r, cy - int(r * 1.25), cx + r, cy + int(r * 1.25)), outline=dark, width=7)
            draw.ellipse((cx - r * 0.35, cy - r * 0.2, cx + r * 0.35, cy + r * 0.55), fill=lerp(base, accent, 0.3))
        for i in range(5):
            y = 80 + i * 180
            draw.arc((60, y, 420, y + 160), 200, 340, fill=vein, width=6)
    else:  # crescent bands — shelter
        for i, y in enumerate(range(40, size, 140)):
            draw.arc((40, y, size - 40, y + 220), 200, 340, fill=dark, width=14)
            if i % 2 == 0:
                draw.arc((180, y + 30, size - 180, y + 180), 210, 330, fill=accent, width=6)
        for x, y in ((200, 300), (700, 500), (400, 800), (850, 200)):
            draw.polygon(((x, y), (x + 22, y + 8), (x + 8, y + 36)), fill=vein)
    for x0, y0, x1, y1 in ((140, 80, 280, 360), (760, 180, 940, 480)):
        draw.line((x0, y0, x1, y1), fill=vein, width=3)
        draw.polygon(((x1, y1), (x1 + 16, y1 - 6), (x1 + 5, y1 + 20)), fill=vein)
    save(img, name)


def paint_shell(size=1024):
    variants = (
        ("tex_shell_tile_1k.png", "tex_shell_n_1k.png", CORAL, CORAL_DK, PLUM, TEAL, "facet"),
        ("tex_shell_teal_1k.png", "tex_shell_teal_n_1k.png", TEAL, (28, 78, 82), MINT, ORCHID, "hex"),
        ("tex_shell_plum_1k.png", "tex_shell_plum_n_1k.png", PLUM, INK, ORCHID, AMBER, "pod"),
        ("tex_shell_cream_1k.png", "tex_shell_cream_n_1k.png", CREAM, CREAM_DK, AMBER, TEAL, "crescent"),
    )
    for tile, nrm, base, dark, accent, vein, motif in variants:
        paint_shell_variant(tile, base, dark, accent, vein, motif, size)
        paint_crystal_normal(size, nrm)
    paint_orm(size, "tex_shell_orm_1k.png", rough=200, metal=0)


def paint_clay_variant(name, base, dark, fleck, size=1024):
    img = Image.new("RGB", (size, size), base)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, size, 36), fill=dark)
    draw.rectangle((0, 500, size, 520), fill=dark)
    for cx, cy, r in ((256, 280, 90), (768, 280, 70), (512, 760, 120), (180, 800, 55)):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=dark, width=8)
        draw.ellipse((cx - int(r * 0.45), cy - int(r * 0.3), cx + int(r * 0.45), cy + int(r * 0.3)), fill=lerp(base, fleck, 0.2))
    for x, y in ((140, 160), (600, 200), (880, 640), (400, 900), (70, 600)):
        draw.polygon(((x, y), (x + 14, y + 4), (x + 6, y + 22)), fill=fleck)
    save(img, name)


def paint_clay(size=1024):
    paint_clay_variant("tex_clay_tile_1k.png", CREAM, CREAM_DK, TEAL, size)
    paint_clay_variant("tex_clay_teal_1k.png", (168, 196, 186), TEAL, ORCHID, size)
    paint_clay_variant("tex_clay_amber_1k.png", (220, 186, 140), AMBER, TEAL, size)
    paint_crystal_normal(size, "tex_clay_n_1k.png")
    paint_orm(size, "tex_clay_orm_1k.png", rough=230, metal=0)


def paint_trim(size=1024):
    img = Image.new("RGB", (size, size), PLUM)
    draw = ImageDraw.Draw(img)
    bands = [(0, 190, CORAL), (200, 370, CREAM), (380, 560, BASALT), (580, 760, TEAL), (780, 1024, ORCHID)]
    for y0, y1, color in bands:
        draw.rectangle((0, y0, size, y1), fill=color)
        draw.rectangle((0, y0, size, y0 + 6), fill=INK)
    # crystal teeth on teal band
    for x in range(40, size, 80):
        draw.polygon(((x, 620), (x + 18, 580), (x + 36, 620), (x + 18, 750)), fill=lerp(TEAL, CREAM, 0.25))
    # double-ring binds
    for x in range(70, size, 140):
        draw.ellipse((x - 22, 820, x + 22, 864), outline=INK, width=4)
        draw.ellipse((x - 8, 834, x + 28, 876), outline=AMBER, width=3)
    # alloy crystal insets
    for x in range(48, size, 110):
        draw.polygon(((x, 430), (x + 16, 400), (x + 32, 430), (x + 16, 520)), fill=ORCHID)
    save(img, "tex_arch_trim_1k.png")
    paint_crystal_normal(size, "tex_arch_trim_n_1k.png")
    paint_orm(size, "tex_arch_trim_orm_1k.png", rough=190, metal=50)


def paint_ground(size=1024):
    img = Image.new("RGB", (size, size), (181, 150, 110))
    draw = ImageDraw.Draw(img)
    px = img.load()
    packed = (155, 118, 78)
    for y in range(size):
        for x in range(size):
            if (x * 3 + y * 5) % 173 == 0:
                px[x, y] = packed
    # mint lichen clusters + crystal grit
    for cx, cy, r in ((200, 180, 40), (620, 260, 28), (400, 700, 36), (860, 820, 24), (120, 880, 30)):
        draw.ellipse((cx - r, cy - r * 0.6, cx + r, cy + r * 0.6), fill=lerp(packed, MINT, 0.45))
    for x, y in ((300, 400), (740, 500), (180, 620), (900, 200), (520, 940)):
        draw.polygon(((x, y), (x + 10, y + 3), (x + 4, y + 16)), fill=TEAL)
    save(img, "tex_ground_packed_1k.png")
    paint_crystal_normal(size, "tex_ground_n_1k.png")
    paint_orm(size, "tex_ground_orm_1k.png", rough=235, metal=0)


def paint_crystal_normal(size, name):
    img = Image.new("RGB", (size, size), (128, 128, 255))
    px = img.load()
    for y in range(0, size, 8):
        for x in range(0, size, 8):
            if ((x * 7 + y * 3) % 97) < 8:
                px[x, y] = (140, 118, 255)
    save(img, name)


def paint_orm(size, name, rough, metal):
    img = Image.new("RGB", (size, size), (20, rough, metal))
    save(img, name)


def main():
    paint_shell()
    paint_clay()
    paint_trim()
    paint_ground()
    print("NPR_TILES_DONE", OUT)


if __name__ == "__main__":
    main()
