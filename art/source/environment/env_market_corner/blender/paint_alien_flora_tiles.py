"""Hand-painted NPR tiles for the alien-green kit (art-bible v1.6 §2/§5.4).

Three new tiles designed with the settlement's shape vocabulary — crescent
ridges, pod ellipses, signal veins — never earth grass/wood/brick:
  tex_frond_alien_1k   frond strip: crescent growth ridges + mint tip wash
  tex_reed_glow_1k     vertical reed fibres + pod speckles
  tex_monolith_glyph_1k slate slab with a carved glyph band (orchid/teal marks)

Run:  python3 art/source/environment/env_market_corner/blender/paint_alien_flora_tiles.py
"""
from __future__ import annotations

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "textures"))

TEAL = (47, 140, 135)
TEAL_DK = (30, 96, 98)
MINT = (120, 201, 164)
MINT_HI = (168, 226, 197)
INDIGO = (52, 51, 94)
BASALT = (75, 82, 104)
BASALT_DK = (46, 52, 70)
ORCHID = (154, 106, 203)
AMBER = (242, 168, 91)
CREAM = (231, 210, 163)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def save(img, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    img.save(path)
    print("ALIEN_TILE", path, img.size)


def vgrad(size, stops):
    """Vertical gradient through colour stops [(t, rgb), ...]."""
    img = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = 0 if t1 == t0 else (t - t0) / (t1 - t0)
                img.putpixel((0, y), lerp(c0, c1, k))
                break
        else:
            img.putpixel((0, y), stops[-1][1])
    return img.resize((size, size))


def crescent(draw, cx, cy, r, thick, col, rot=0.0, squash=1.0):
    """The settlement's core motif: a thick crescent arc (§1.3 弯月)."""
    box = (cx - r, cy - r * squash, cx + r, cy + r * squash)
    draw.arc(box, rot, rot + 200, fill=col, width=thick)


def paint_frond():
    size = 1024
    rng = random.Random(31)
    img = vgrad(size, [(0.0, TEAL_DK), (0.45, TEAL), (0.8, MINT), (1.0, MINT_HI)])
    draw = ImageDraw.Draw(img)
    # crescent growth ridges march up the frond, shrinking toward the tip
    y = size - 30
    i = 0
    while y > 40:
        t = 1.0 - y / size
        w = int(470 * (1.0 - 0.55 * t))
        thick = max(3, int(14 * (1.0 - 0.6 * t)))
        col = lerp(TEAL_DK, MINT, t)
        cx = size / 2 + (18 if i % 2 else -18) * (1.0 - t)
        crescent(draw, cx, y, w, thick, col, rot=170 if i % 2 else 190, squash=0.34)
        y -= int(58 + 26 * (1.0 - t))
        i += 1
    # central stalk
    draw.line((size / 2, size, size / 2 + 26, 0), fill=lerp(TEAL_DK, INDIGO, 0.4), width=16)
    draw.line((size / 2, size, size / 2 + 26, 0), fill=MINT, width=5)
    # sparse signal veins (orchid) — direction hints, not noise
    for (x0, y0, x1, y1) in ((120, 900, 300, 690), (760, 820, 640, 600), (220, 420, 380, 260), (820, 360, 700, 180)):
        draw.line((x0, y0, x1, y1), fill=lerp(ORCHID, TEAL, 0.35), width=6)
        draw.ellipse((x1 - 9, y1 - 9, x1 + 9, y1 + 9), fill=lerp(ORCHID, MINT, 0.4))
    # pod speckles along the edges
    for _ in range(26):
        x = rng.randint(60, size - 60)
        y = rng.randint(120, size - 60)
        r = rng.randint(4, 9)
        draw.ellipse((x - r, y - r * 2, x + r, y + r * 2), outline=lerp(MINT, CREAM, 0.3), width=2)
    img = img.filter(ImageFilter.GaussianBlur(1.1))
    save(img, "tex_frond_alien_1k.png")


def paint_reed():
    size = 1024
    rng = random.Random(77)
    img = vgrad(size, [(0.0, INDIGO), (0.35, TEAL_DK), (0.75, TEAL), (1.0, MINT)])
    draw = ImageDraw.Draw(img)
    # vertical reed fibres
    x = 20
    while x < size:
        w = rng.randint(8, 22)
        col = lerp(TEAL_DK, TEAL, rng.random())
        draw.line((x, 0, x + rng.randint(-30, 30), size), fill=col, width=w)
        x += w + rng.randint(6, 20)
    # a few pale stalk highlights
    for _ in range(9):
        x = rng.randint(40, size - 40)
        draw.line((x, rng.randint(0, 200), x + rng.randint(-20, 20), size), fill=lerp(MINT, CREAM, 0.25), width=4)
    # glow pods: ellipse heads with mint cores, sparse
    for _ in range(12):
        cx, cy = rng.randint(80, size - 80), rng.randint(80, size - 80)
        r = rng.randint(16, 30)
        draw.ellipse((cx - r, cy - int(r * 1.5), cx + r, cy + int(r * 1.5)),
                     fill=lerp(TEAL, INDIGO, 0.3), outline=MINT, width=4)
        draw.ellipse((cx - r * 0.4, cy - r * 0.6, cx + r * 0.4, cy + r * 0.6), fill=MINT_HI)
        crescent(draw, cx, cy, r + 14, 3, lerp(MINT, TEAL, 0.4), rot=rng.uniform(0, 360), squash=0.8)
    img = img.filter(ImageFilter.GaussianBlur(1.0))
    save(img, "tex_reed_glow_1k.png")


def paint_monolith():
    size = 1024
    rng = random.Random(11)
    img = vgrad(size, [(0.0, BASALT_DK), (0.4, BASALT), (0.7, BASALT_DK), (1.0, (38, 44, 62))])
    draw = ImageDraw.Draw(img)
    # broad directional wear bands (§5.4: 大块、定向的修补痕迹)
    for (y0, y1, alpha) in ((80, 240, 0.16), (430, 560, 0.12), (760, 900, 0.2)):
        band = Image.new("RGB", (size, y1 - y0), lerp(BASALT, CREAM, alpha))
        img.paste(band, (0, y0))
    # glyph band: a readable horizontal row of carved marks (orchid/teal)
    band_y0, band_y1 = 380, 660
    draw.rectangle((0, band_y0, size, band_y1), fill=lerp(BASALT_DK, INDIGO, 0.45))
    draw.line((0, band_y0, size, band_y0), fill=lerp(MINT, TEAL, 0.3), width=6)
    draw.line((0, band_y1, size, band_y1), fill=lerp(MINT, TEAL, 0.3), width=6)
    glyphs = []
    cx = 70
    while cx < size - 70:
        kind = rng.randrange(5)
        col = lerp(ORCHID, MINT, rng.random() * 0.6)
        cy = (band_y0 + band_y1) // 2
        r = rng.randint(22, 40)
        if kind == 0:
            crescent(draw, cx, cy, r, 9, col, rot=rng.uniform(140, 220), squash=1.0)
        elif kind == 1:  # concentric pods
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=8)
            draw.ellipse((cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2), outline=col, width=5)
        elif kind == 2:  # stacked bars
            for k in range(3):
                draw.line((cx - r, cy - 24 + k * 24, cx + r, cy - 24 + k * 24), fill=col, width=9)
        elif kind == 3:  # dot triangle (seed)
            for dx, dy in ((0, -r), (-r, r // 2), (r, r // 2)):
                draw.ellipse((cx + dx - 8, cy + dy - 8, cx + dx + 8, cy + dy + 8), fill=col)
        else:  # diagonal signal vein
            draw.line((cx - r, cy + r, cx + r, cy - r), fill=col, width=8)
            draw.ellipse((cx + r - 7, cy - r - 7, cx + r + 7, cy - r + 7), fill=lerp(col, AMBER, 0.4))
        cx += rng.randint(96, 150)
    # worn scratches across everything (directional, not noise)
    for _ in range(22):
        x0 = rng.randint(0, size)
        y0 = rng.randint(0, size)
        x1 = x0 + rng.randint(-140, 140)
        y1 = y0 + rng.randint(-40, 40)
        draw.line((x0, y0, x1, y1), fill=lerp(BASALT, (200, 205, 220), 0.28), width=2)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    save(img, "tex_monolith_glyph_1k.png")


def main():
    paint_frond()
    paint_reed()
    paint_monolith()


if __name__ == "__main__":
    main()
