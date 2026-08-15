"""Alien-green kit for the valley meadows (art-bible v1.6 §3.7 / §5.6).

Three hand-modeled assets + the three hand-painted tiles from
paint_alien_flora_tiles.py:

  fol_frond_alien_a  curl-frond cluster — six ribbons that rise, bow and curl
                     over; tex_frond_alien_1k crescent ridges; canopy mesh is
                     named "frond_canopy" so the Godot sway shader hooks it
  fol_reed_glow_a    glow reeds — thin S-curved stalks with mint pod heads;
                     stem contains "glow" so the existing paint rule lights
                     the pods at dusk
  prp_monolith_a     relic monolith — rounded-top basalt slab (NOT a spike),
                     proud glyph band (tex_monolith_glyph_1k), ceramic footing
                     and one alloy repair patch (§5.3 ≥1 处修补)

Z-up authored, origin at base. No cones anywhere — the settlement just
recovered from pyramid poisoning.

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/environment/env_market_corner/blender/model_alien_greens.py
"""
from __future__ import annotations

import math
import os
import random as _r

import bmesh
import bpy
from mathutils import Matrix

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
BLEND = os.path.join(HERE, "blender/env_alien_greens.blend")
EXPORT_DIR = os.path.join(HERE, "export")
TEX_DIR = os.path.join(HERE, "textures")

PAL = {
    "tide_teal": (0x2F / 255, 0x8C / 255, 0x87 / 255, 1.0),
    "lichen_mint": (0x78 / 255, 0xC9 / 255, 0xA4 / 255, 1.0),
    "dusk_indigo": (0x34 / 255, 0x33 / 255, 0x5E / 255, 1.0),
    "basalt": (0x4B / 255, 0x52 / 255, 0x68 / 255, 1.0),
    "dust_cream": (0xE7 / 255, 0xD2 / 255, 0xA3 / 255, 1.0),
    "bark_plum": (0x5A / 255, 0x3F / 255, 0x58 / 255, 1.0),
}

ORCHID = (0x9A / 255, 0x6A / 255, 0xCB / 255, 1.0)
ROOT_TEAL = (0.13, 0.30, 0.32, 1.0)
TIP_MINT = (0.55, 0.86, 0.68, 1.0)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mat(name, color, roughness=0.9):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def hook_image(mat, image_path, is_color=True):
    if not os.path.isfile(image_path) or mat is None or not mat.use_nodes:
        return
    img = bpy.data.images.load(image_path, check_existing=True)
    img.colorspace_settings.name = "sRGB" if is_color else "Non-Color"
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        return
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.location = (-320, 200 if is_color else 0)
    if is_color:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Normal"])


def lerp_color(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, 1.0)


def new_fam():
    return {"bm": bmesh.new(), "col": {}}


def paint(fam, verts, color):
    for vert in verts:
        fam["col"][vert] = color


def finish_family(fam, name, fallback, mat, collection):
    bm = fam["bm"]
    if len(bm.verts) == 0:
        bm.free()
        return None
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table()
    colors_by_index = [fam["col"].get(vert, fallback) for vert in bm.verts]
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    attr = mesh.color_attributes.new(name="Color", domain="CORNER", type="FLOAT_COLOR")
    for loop in mesh.loops:
        attr.data[loop.index].color = colors_by_index[loop.vertex_index]
    if mesh.uv_layers.get("UVMap") is None:
        mesh.uv_layers.new(name="UVMap")
    uv = mesh.uv_layers["UVMap"]
    for poly in mesh.polygons:
        n = poly.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for li, vi in zip(poly.loop_indices, poly.vertices):
            co = mesh.vertices[vi].co
            if az >= ax and az >= ay:
                u, v = co.x, co.y
            elif ay >= ax:
                u, v = co.x, co.z
            else:
                u, v = co.y, co.z
            uv.data[li].uv = (u * 0.55, v * 0.55)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def set_uv_window(mesh, u0, v0, u1, v1):
    """Force all UVs into a rect (for the glyph band strip)."""
    if mesh.uv_layers.get("UVMap") is None:
        mesh.uv_layers.new(name="UVMap")
    uv = mesh.uv_layers["UVMap"]
    xs = [v.co.x for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    x_min, x_max = min(xs), max(xs)
    z_min, z_max = min(zs), max(zs)
    for li in range(len(mesh.loops)):
        vi = mesh.loops[li].vertex_index
        co = mesh.vertices[vi].co
        tu = 0.5 if x_max == x_min else (co.x - x_min) / (x_max - x_min)
        tv = 0.5 if z_max == z_min else (co.z - z_min) / (z_max - z_min)
        uv.data[li].uv = (u0 + (u1 - u0) * tu, v0 + (v1 - v0) * tv)


def add_double_quad(bm, colors, v0, v1, v2, v3, c_lo, c_hi):
    """Two-sided quad: front + flipped copy on duplicated verts (bmesh forbids
    reusing the same verts with opposite winding), so thin blades never vanish."""
    quad = bm.faces.new((v0, v1, v2, v3))
    for loop in quad.loops:
        colors[loop.vert] = c_lo if loop.vert in (v0, v1) else c_hi
    b0 = bm.verts.new(v0.co.copy())
    b1 = bm.verts.new(v1.co.copy())
    b2 = bm.verts.new(v2.co.copy())
    b3 = bm.verts.new(v3.co.copy())
    back = bm.faces.new((b3, b2, b1, b0))
    for loop in back.loops:
        colors[loop.vert] = c_lo if loop.vert in (b0, b1) else c_hi


# ================================================================ frond cluster
def add_curl_frond(fam, base, angle, height, reach, curl_r, width, tint, segs=9):
    """One curling frond ribbon.

    Spine: rises from `base`, leans outward `reach`, then wraps forward around
    a small circle of radius `curl_r` so the tip curls over like a fiddlehead
    minus the spiral. Built as an explicit strip so every row carries the
    root-to-tip gradient.
    """
    bm = fam["bm"]
    lx, ly = math.cos(angle), math.sin(angle)
    # spine samples
    pts = []
    rise_h = height - curl_r * 0.9
    for i in range(segs + 1):
        t = i / segs
        if t < 0.68:
            k = t / 0.68
            # outward-bowing rise
            bow = math.sin(k * math.pi) * 0.16
            px = base[0] + lx * reach * k + lx * bow
            py = base[1] + ly * reach * k + ly * bow
            pz = base[2] + rise_h * (k ** 1.25)
        else:
            k = (t - 0.68) / 0.32
            cxp = base[0] + lx * reach
            cyp = base[1] + ly * reach
            czp = base[2] + rise_h
            # curl: circle in the (outward, up) plane, rolling forward
            a = -0.35 + k * (math.pi * 0.92)
            px = cxp + lx * math.sin(a) * curl_r
            py = cyp + ly * math.sin(a) * curl_r
            pz = czp + (1.0 - math.cos(max(0.0, a))) * curl_r * -0.9 + curl_r * math.sin(a) * 0.9
        pts.append((px, py, pz, t))
    side = (-ly, lx)
    rows = []
    for (px, py, pz, t) in pts:
        w = width * (1.0 - 0.78 * t) * 0.5
        a = bm.verts.new((px + side[0] * w, py + side[1] * w, pz))
        b = bm.verts.new((px - side[0] * w, py - side[1] * w, pz))
        rows.append((a, b, t))
    for i in range(segs):
        t0, t1 = rows[i][2], rows[i + 1][2]
        c0 = lerp_color(ROOT_TEAL, PAL["tide_teal"], min(1.0, t0 * 1.7))
        c1 = lerp_color(PAL["tide_teal"], TIP_MINT, max(0.0, (t1 - 0.4) / 0.6))
        c0 = lerp_color(c0, tint, 0.20)
        c1 = lerp_color(c1, tint, 0.20)
        add_double_quad(bm, fam["col"], rows[i][0], rows[i][1], rows[i + 1][1], rows[i + 1][0], c0, c1)


def build_fronds(col, lod, mats):
    p = f"lod{lod}__frond"
    canopy, root = new_fam(), new_fam()
    rng = _r.Random(41 + lod)
    n = 7 if lod == 0 else (4 if lod == 1 else 3)
    tints = [PAL["tide_teal"], PAL["lichen_mint"], ORCHID, PAL["dusk_indigo"]]
    for i in range(n):
        ang = math.tau * i / n + rng.uniform(-0.25, 0.25)
        h = 0.95 + rng.uniform(0.0, 0.45)
        add_curl_frond(
            canopy, (0.0, 0.0, 0.05), ang,
            h, 0.34 + rng.uniform(0.0, 0.30),
            0.20 + rng.uniform(0.0, 0.14),
            0.16 if lod == 0 else 0.20,
            tints[rng.randrange(4)],
            segs=9 if lod == 0 else 6,
        )
    # ceramic root collar + fibre bind: roots fixed, canopy sways (§5.4)
    ret = bmesh.ops.create_cone(root["bm"], radius1=0.20, radius2=0.10, depth=0.14, cap_ends=True, segments=8)
    bmesh.ops.translate(root["bm"], vec=(0, 0, 0.07), verts=ret["verts"])
    paint(root, ret["verts"], PAL["dust_cream"])
    ret2 = bmesh.ops.create_cone(root["bm"], radius1=0.115, radius2=0.115, depth=0.05, cap_ends=True, segments=8)
    bmesh.ops.translate(root["bm"], vec=(0, 0, 0.17), verts=ret2["verts"])
    paint(root, ret2["verts"], PAL["dusk_indigo"])
    finish_family(canopy, p + "_canopy", PAL["tide_teal"], mats["canopy"], col)
    finish_family(root, p + "_root", PAL["dust_cream"], mats["root"], col)


# ================================================================ glow reeds
def build_reeds(col, lod, mats):
    p = f"lod{lod}__reed_glow"
    stems, pods = new_fam(), new_fam()
    rng = _r.Random(83 + lod)
    n = 9 if lod == 0 else (6 if lod == 1 else 4)
    for i in range(n):
        ang = rng.uniform(0.0, math.tau)
        rad = rng.uniform(0.05, 0.30)
        bx, bz = math.cos(ang) * rad, math.sin(ang) * rad
        h = 0.85 + rng.uniform(0.0, 0.6)
        lean = rng.uniform(0.10, 0.26)
        # S-curved stalk as a 4-seg strip, very narrow
        segs = 4
        lx, ly = math.cos(ang), math.sin(ang)
        pts = []
        for s in range(segs + 1):
            t = s / segs
            sway = math.sin(t * math.pi * 1.6 + ang * 2.0) * 0.08
            px = bx + lx * (lean * h * t) + lx * sway
            py = bz + ly * (lean * h * t) + ly * sway
            pz = h * t
            pts.append((px, py, pz, t))
        side = (-ly, lx)
        rows = []
        for (px, py, pz, t) in pts:
            w = 0.030 * (1.0 - 0.6 * t)
            a = stems["bm"].verts.new((px + side[0] * w, py + side[1] * w, pz))
            b = stems["bm"].verts.new((px - side[0] * w, py - side[1] * w, pz))
            rows.append((a, b, t))
        for s in range(segs):
            t0, t1 = rows[s][2], rows[s + 1][2]
            c0 = lerp_color(ROOT_TEAL, PAL["tide_teal"], min(1.0, t0 * 1.8))
            c1 = lerp_color(PAL["tide_teal"], PAL["lichen_mint"], max(0.0, (t1 - 0.5) / 0.5))
            add_double_quad(stems["bm"], stems["col"], rows[s][0], rows[s][1], rows[s + 1][1], rows[s + 1][0], c0, c1)
        # pod head: squashed sphere with a collar ring
        tip = pts[-1]
        ret = bmesh.ops.create_uvsphere(pods["bm"], u_segments=8, v_segments=5, radius=0.055 + rng.uniform(0.0, 0.03))
        bmesh.ops.scale(pods["bm"], vec=(1.0, 1.0, 1.5), verts=ret["verts"])
        bmesh.ops.translate(pods["bm"], vec=(tip[0], tip[1], tip[2] + 0.07), verts=ret["verts"])
        paint(pods, ret["verts"], PAL["lichen_mint"])
        ring = bmesh.ops.create_cone(pods["bm"], radius1=0.05, radius2=0.05, depth=0.018, cap_ends=False, segments=8)
        bmesh.ops.translate(pods["bm"], vec=(tip[0], tip[1], tip[2] - 0.01), verts=ring["verts"])
        paint(pods, ring["verts"], PAL["dusk_indigo"])
    # shared root mat so the cluster reads as one plant
    ret = bmesh.ops.create_cone(stems["bm"], radius1=0.16, radius2=0.06, depth=0.09, cap_ends=True, segments=8)
    bmesh.ops.translate(stems["bm"], vec=(0, 0, 0.045), verts=ret["verts"])
    paint(stems, ret["verts"], PAL["dusk_indigo"])
    finish_family(stems, p + "_stems", PAL["tide_teal"], mats["stem"], col)
    finish_family(pods, p + "_pods", PAL["lichen_mint"], mats["pod"], col)


# ================================================================ monolith
def build_monolith(col, lod, mats, stem="monolith"):
    p = f"lod{lod}__{stem}"
    slab, glyphs, foot, patch = new_fam(), new_fam(), new_fam(), new_fam()
    w, h, thick = 1.15, 2.6, 0.38
    bm = slab["bm"]
    # rounded-top slab profile (right side up, semicircle crown, left side down)
    pts = []
    seg_side = 4
    for i in range(seg_side + 1):
        t = i / seg_side
        pts.append((w / 2, h * 0.72 * t))
    arc_n = 7
    for i in range(arc_n):
        a = math.pi * (i + 1) / (arc_n + 1)
        pts.append((math.cos(a) * w / 2, h * 0.72 + math.sin(a) * h * 0.28))
    for i in range(seg_side + 1):
        t = 1.0 - i / seg_side
        pts.append((-w / 2, h * 0.72 * t))
    verts = [bm.verts.new((x, 0.0, z)) for (x, z) in pts]
    face = bm.faces.new(verts)
    orig_verts = set(bm.verts)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    new_verts = [v for v in ret["geom"] if isinstance(v, bmesh.types.BMVert) and v not in orig_verts]
    bmesh.ops.translate(bm, vec=(0.0, thick, 0.0), verts=new_verts)
    # taper the front face slightly so the slab reads hand-set
    for v in bm.verts:
        if v.co.y > thick * 0.9:
            v.co.x *= 0.92
            v.co.z *= 0.985
    paint(slab, bm.verts, PAL["basalt"])
    # subtle vertex gradient: darker at the buried base
    for v in bm.verts:
        k = min(1.0, v.co.z / (h * 0.5))
        slab["col"][v] = lerp_color((0.16, 0.18, 0.24, 1.0), PAL["basalt"], 0.35 + 0.65 * k)

    # glyph band: proud strip on the front face, UVs locked to the band
    gz0, gz1 = h * 0.42, h * 0.78
    g = glyphs["bm"]
    box = bmesh.ops.create_cube(g, size=1.0)
    bmesh.ops.scale(g, vec=(w * 0.94, 0.045, gz1 - gz0), verts=box["verts"])
    bmesh.ops.translate(g, vec=(0.0, thick + 0.02, (gz0 + gz1) / 2), verts=box["verts"])
    paint(glyphs, box["verts"], PAL["dusk_indigo"])

    # footing: cast ceramic ring + two settled rubble blocks
    f = foot["bm"]
    ret = bmesh.ops.create_cone(f, radius1=0.85, radius2=0.70, depth=0.16, cap_ends=True, segments=10)
    bmesh.ops.translate(f, vec=(0.0, 0.0, 0.08), verts=ret["verts"])
    paint(foot, ret["verts"], PAL["dust_cream"])
    ret = bmesh.ops.create_cone(f, radius1=0.34, radius2=0.42, depth=0.10, cap_ends=True, segments=8)
    bmesh.ops.translate(f, vec=(0.0, 0.0, 0.20), verts=ret["verts"])
    paint(foot, ret["verts"], PAL["bark_plum"])
    if lod == 0:
        for (bx, bz, s, rz) in ((-0.72, 0.34, 0.16, 0.4), (0.66, -0.30, 0.12, -0.7)):
            rb = bmesh.ops.create_cube(f, size=1.0)
            bmesh.ops.scale(f, vec=(s, s * 1.4, s * 0.7), verts=rb["verts"])
            bmesh.ops.translate(f, vec=(bx, bz, s * 0.35), verts=rb["verts"])
            bmesh.ops.rotate(f, matrix=Matrix.Rotation(rz, 4, "Z"), verts=rb["verts"])
            paint(foot, rb["verts"], lerp_color(PAL["basalt"], PAL["dust_cream"], 0.4))

    # alloy repair patch champing the broken top edge (§5.3 修补)
    a = patch["bm"]
    pb = bmesh.ops.create_cube(a, size=1.0)
    bmesh.ops.scale(a, vec=(0.34, thick * 0.7, 0.16), verts=pb["verts"])
    bmesh.ops.translate(a, vec=(-w * 0.22, thick * 0.5, h * 0.83), verts=pb["verts"])
    bmesh.ops.rotate(a, matrix=Matrix.Rotation(0.16, 4, "X"), verts=pb["verts"])
    paint(patch, pb["verts"], (0.42, 0.46, 0.58, 1.0))
    for dx in (-0.10, 0.10):
        riv = bmesh.ops.create_cone(a, radius1=0.018, radius2=0.018, depth=thick * 0.8, cap_ends=True, segments=6)
        bmesh.ops.translate(a, vec=(-w * 0.22 + dx, thick * 0.5, h * 0.83), verts=riv["verts"])
        bmesh.ops.rotate(a, matrix=Matrix.Rotation(math.pi / 2, 4, "X"), verts=riv["verts"])
        paint(patch, riv["verts"], (0.62, 0.65, 0.74, 1.0))

    slab_obj = finish_family(slab, p + "_slab", PAL["basalt"], mats["slab"], col)
    glyph_obj = finish_family(glyphs, p + "_glyphs", PAL["dusk_indigo"], mats["glyph"], col)
    finish_family(foot, p + "_foot", PAL["dust_cream"], mats["foot"], col)
    finish_family(patch, p + "_patch", (0.42, 0.46, 0.58, 1.0), mats["patch"], col)
    if glyph_obj is not None and slab_obj is not None:
        set_uv_window(glyph_obj.data, 0.02, 0.36, 0.98, 0.64)


# ================================================================ fallen monolith
def build_monolith_fallen(col, lod, mats):
    """prp_monolith_fallen_a — the ORIGINAL toppled pose, baked (v2).

    Review history: v1 stood the asset up and rotated it at runtime — the
    footing wheel's near-tangent bottom rim z-fought the ground plane and
    flashed black along the contact arc. v2-lying flattened the slab on its
    back; review rejected the pose AND its leaning fragment hovered.
    This version rebuilds the liked silhouette (slab tipped ~84 deg, glyph
    face skyward, head raised ~6 deg, base held by its footing wheel) but:
      - the pose is baked per-object, so UVs stay correct;
      - the whole body is lifted 0.26 m so the footing wheel bites DEEP
        (bottom at -0.48 m) — the rim crosses the ground plane steeply on
        both sides, no tangent band, no flicker;
      - instead of a hovering fragment, a half-buried rubble berm nests the
        wheel and reads as the soil the slab slammed into.
    """
    build_monolith(col, lod, mats, stem="monolith_fallen")
    topple = (
        Matrix.Rotation(0.35, 4, "Z")
        @ Matrix.Rotation(math.radians(84.0), 4, "X")
        @ Matrix.Diagonal((0.88, 0.88, 0.88, 1.0))
    )
    prefix = f"lod{lod}__monolith_fallen"
    for obj in list(col.objects):
        if obj.name.startswith(prefix):
            obj.matrix_basis = topple @ obj.matrix_basis
            obj.location.z += 0.26
    if lod <= 1:
        berm = new_fam()
        # every stone is sunk (centre below half-height): nothing hovers
        for (bx, by, sx, sy, sz, rz) in (
            (0.62, -0.12, 0.20, 0.30, 0.16, 0.5),
            (-0.58, -0.20, 0.17, 0.26, 0.14, -0.4),
            (0.10, -0.52, 0.16, 0.34, 0.13, 0.9),
            (-0.16, 0.42, 0.14, 0.24, 0.12, 0.2),
        ):
            rb = bmesh.ops.create_cube(berm["bm"], size=1.0)
            bmesh.ops.scale(berm["bm"], vec=(sx, sy, sz), verts=rb["verts"])
            bmesh.ops.translate(berm["bm"], vec=(bx, by, sz * 0.32), verts=rb["verts"])
            bmesh.ops.rotate(berm["bm"], matrix=Matrix.Rotation(rz, 4, "Z"), verts=rb["verts"])
            paint(berm, rb["verts"], lerp_color(PAL["basalt"], PAL["dust_cream"], 0.4))
        finish_family(berm, f"lod{lod}__monolith_fallen_berm", PAL["dust_cream"], mats["foot"], col)


def export_glb(name):
    out = os.path.join(EXPORT_DIR, name + ".glb")
    bpy.ops.object.select_all(action="DESELECT")
    col = bpy.data.collections[name]
    for obj in col.objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=out,
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=True,
        export_vertex_color="ACTIVE",
    )
    print(f"GREEN_KIT_EXPORT {name} ({os.path.getsize(out) / 1024:.0f} KB)")


def count_tris(col):
    total = 0
    for obj in col.objects:
        mesh = obj.data
        if not hasattr(mesh, "polygons"):
            continue
        for poly in mesh.polygons:
            total += len(poly.vertices) - 2
    return total


def main():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    reset_scene()

    frond_mats = {
        "canopy": make_mat("mat_frond_canopy", PAL["tide_teal"], 0.9),
        "root": make_mat("mat_frond_root", PAL["dust_cream"], 0.9),
    }
    hook_image(frond_mats["canopy"], os.path.join(TEX_DIR, "tex_frond_alien_1k.png"), True)
    col = bpy.data.collections.new("fol_frond_alien_a")
    bpy.context.scene.collection.children.link(col)
    for lod in (0, 1, 2):
        build_fronds(col, lod, frond_mats)
    print("GREEN_KIT_TRIS fol_frond_alien_a", count_tris(col))
    export_glb("fol_frond_alien_a")

    reed_mats = {
        "stem": make_mat("mat_reed_stem", PAL["tide_teal"], 0.9),
        "pod": make_mat("mat_reed_pod", PAL["lichen_mint"], 0.8),
    }
    hook_image(reed_mats["stem"], os.path.join(TEX_DIR, "tex_reed_glow_1k.png"), True)
    col = bpy.data.collections.new("fol_reed_glow_a")
    bpy.context.scene.collection.children.link(col)
    for lod in (0, 1, 2):
        build_reeds(col, lod, reed_mats)
    print("GREEN_KIT_TRIS fol_reed_glow_a", count_tris(col))
    export_glb("fol_reed_glow_a")

    mono_mats = {
        "slab": make_mat("mat_monolith_slab", PAL["basalt"], 0.92),
        "glyph": make_mat("mat_monolith_glyph", PAL["dusk_indigo"], 0.85),
        "foot": make_mat("mat_monolith_foot", PAL["dust_cream"], 0.9),
        "patch": make_mat("mat_monolith_patch", (0.42, 0.46, 0.58, 1.0), 0.55),
    }
    hook_image(mono_mats["slab"], os.path.join(TEX_DIR, "tex_monolith_glyph_1k.png"), True)
    hook_image(mono_mats["glyph"], os.path.join(TEX_DIR, "tex_monolith_glyph_1k.png"), True)
    col = bpy.data.collections.new("prp_monolith_a")
    bpy.context.scene.collection.children.link(col)
    for lod in (0, 1):
        build_monolith(col, lod, mono_mats)
    print("GREEN_KIT_TRIS prp_monolith_a", count_tris(col))
    export_glb("prp_monolith_a")

    col = bpy.data.collections.new("prp_monolith_fallen_a")
    bpy.context.scene.collection.children.link(col)
    for lod in (0, 1):
        build_monolith_fallen(col, lod, mono_mats)
    print("GREEN_KIT_TRIS prp_monolith_fallen_a", count_tris(col))
    export_glb("prp_monolith_fallen_a")

    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print("GREEN_KIT_DONE")


if __name__ == "__main__":
    main()
