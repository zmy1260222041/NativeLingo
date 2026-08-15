"""fol_ground_tufts_a v02 — alien grass blades replace the v01 cone tufts.

v01 scattered ~500 five-segment cones ("pyramids") along the path edges and
the settlement rim; in-game they read as teal tetrahedron litter. v02 keeps
the exact same spot layout (same seeds / PATHS) but draws each spot as a
cluster of 3-4 bent, tapering blades with a baked dusk-teal -> lichen-mint
vertex gradient, plus the original basalt pebbles.

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/environment/env_market_corner/blender/model_env_tufts_v02.py
"""
from __future__ import annotations

import math
import os
import random as _r

import bmesh
import bpy

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
BLEND = os.path.join(HERE, "blender/env_tufts_v02.blend")
EXPORT_DIR = os.path.join(HERE, "export")

PAL = {
    "tide_teal": (0x2F / 255, 0x8C / 255, 0x87 / 255, 1.0),
    "lichen_mint": (0x78 / 255, 0xC9 / 255, 0xA4 / 255, 1.0),
    "dusk_indigo": (0x34 / 255, 0x33 / 255, 0x5E / 255, 1.0),
    "basalt": (0x4B / 255, 0x52 / 255, 0x68 / 255, 1.0),
    "dust_cream": (0xE7 / 255, 0xD2 / 255, 0xA3 / 255, 1.0),
}

BLADE_BASE = (0.16, 0.34, 0.35, 1.0)   # dusk teal root
BLADE_MID = PAL["tide_teal"]
BLADE_TIP = (0.55, 0.86, 0.68, 1.0)    # pale mint tip

PATHS = [
    [(0, 0.4), (-0.9, 1.1), (-1.8, 1.6)],
    [(0, 0), (-2.4, 1.7), (-4.6, 3.5), (-6.0, 4.3)],
    [(0, 0), (2.2, 2.7), (4.0, 5.2), (5.0, 6.3)],
    [(0.8, -0.6), (3.4, -1.7), (6.0, -2.7), (7.8, -3.1)],
    [(-1.2, -0.8), (-3.8, -2.5), (-5.9, -4.5), (-6.9, -5.3)],
    [(0, -1.2), (0, -4.0), (0, -7.4)],
    [(-1.9, 1.5), (-2.9, 1.9)],
    [(1.2, -4.5), (1.8, -7.6), (2.0, -8.7)],
    [(7.0, -3.4), (9.4, -5.4), (9.9, -7.5)],
    [(-5.5, -4.4), (-7.3, -3.3)],
    [(1.4, -0.5), (2.6, -0.5)],
]


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mat(name, color, roughness=0.95):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def lerp_color(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, 1.0)


def add_blade(bm, colors, base_xy, blade_h, lean_dir, lean_amt, curl, width, tint):
    """One bent grass blade: 3 quads, tapering, curling over at the tip.

    Built as explicit vertices so each row can carry its gradient color and
    the tip stays a clean point (no cone caps, no pyramid silhouettes).
    """
    segs = 3
    x0, y0 = base_xy
    lx, ly = lean_dir
    prev = None
    pts = []
    cx, cy, cz = float(x0), float(y0), 0.0
    for i in range(segs + 1):
        v = i / segs
        if i > 0:
            step = blade_h / segs
            # lean grows with height, then the last segment curls outward
            curl_k = curl if i == segs else 0.0
            cx += (lx * lean_amt + lx * curl_k) * step
            cy += (ly * lean_amt + ly * curl_k) * step
            cz += step * (1.0 if i < segs else 0.55)
        pts.append((cx, cy, cz, v))
    side = (-ly, lx)
    rows = []
    for (px, py, pz, v) in pts:
        w = width * (1.0 - 0.72 * v) * 0.5
        a = bm.verts.new((px + side[0] * w, py + side[1] * w, pz))
        b = bm.verts.new((px - side[0] * w, py - side[1] * w, pz))
        rows.append((a, b, v))
    for i in range(segs):
        v0, v1 = rows[i][2], rows[i + 1][2]
        c0 = lerp_color(BLADE_BASE, BLADE_MID, min(1.0, v0 * 1.6))
        c1 = lerp_color(BLADE_MID, BLADE_TIP, max(0.0, (v1 - 0.45) / 0.55))
        c0 = lerp_color(c0, tint, 0.22)
        c1 = lerp_color(c1, tint, 0.22)
        a0, b0v = rows[i][0], rows[i][1]
        a1, b1v = rows[i + 1][0], rows[i + 1][1]
        quad = bm.faces.new((a0, b0v, b1v, a1))
        for loop in quad.loops:
            colors[loop.vert] = c0 if loop.vert in (a0, b0v) else c1
        # duplicated flipped copy — blades are too thin to gamble on winding
        fa0 = bm.verts.new(a0.co.copy())
        fb0 = bm.verts.new(b0v.co.copy())
        fb1 = bm.verts.new(b1v.co.copy())
        fa1 = bm.verts.new(a1.co.copy())
        back = bm.faces.new((fa1, fb1, fb0, fa0))
        for loop in back.loops:
            colors[loop.vert] = c0 if loop.vert in (fa0, fb0) else c1


def finish_mesh(bm, colors, name, mat, collection):
    fallback = PAL["tide_teal"]
    mesh = bpy.data.meshes.new(name + "_mesh")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table()
    colors_by_index = [colors.get(vert, fallback) for vert in bm.verts]
    bm.to_mesh(mesh)
    attr = mesh.color_attributes.new(name="Color", domain="CORNER", type="FLOAT_COLOR")
    for loop in mesh.loops:
        attr.data[loop.index].color = colors_by_index[loop.vertex_index]
    bm.free()
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
            uv.data[li].uv = (u * 0.9, v * 0.9)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def build_tufts(col):
    prefix = "fol_ground_tufts_a"
    mat = make_mat("mat_fol_tufts", PAL["tide_teal"], roughness=0.95)
    bm_t = bmesh.new()
    bm_p = bmesh.new()
    colors_t = {}
    _r.seed(5)
    edge_spots = []
    for i in range(64):
        a = math.tau * i / 64 + _r.uniform(-0.05, 0.05)
        r = 12.6 + _r.uniform(-0.6, 1.6)
        edge_spots.append((math.cos(a) * r, math.sin(a) * r))
    for pts in PATHS:
        for j in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[j], pts[j + 1]
            seg_len = math.hypot(bx - ax, by - ay)
            steps = max(1, int(seg_len / 0.33))
            nx, ny = -(by - ay) / max(1e-5, seg_len), (bx - ax) / max(1e-5, seg_len)
            for k in range(steps):
                t = k / steps
                px, py = ax + (bx - ax) * t, ay + (by - ay) * t
                for side in (-1, 1):
                    if _r.random() < 0.5:
                        edge_spots.append((px + nx * side * (0.72 + _r.uniform(0, 0.55)),
                                           py + ny * side * (0.72 + _r.uniform(0, 0.55))))
    for i in range(40):
        a = math.tau * i / 40
        edge_spots.append((math.cos(a) * (5.8 + _r.uniform(0, 0.7)), math.sin(a) * (5.8 + _r.uniform(0, 0.7))))
    tints = [PAL["tide_teal"], PAL["lichen_mint"], PAL["dusk_indigo"]]
    blade_count = 0
    for (tx, ty) in edge_spots:
        if _r.random() < 0.86:
            n = 3 + (1 if _r.random() < 0.4 else 0)
            for bi in range(n):
                ang = _r.uniform(0.0, math.tau)
                lean = (math.cos(ang), math.sin(ang))
                bh = 0.14 + _r.uniform(0.0, 0.16)
                off = (_r.uniform(-0.055, 0.055), _r.uniform(-0.055, 0.055))
                add_blade(
                    bm_t, colors_t, (tx + off[0], ty + off[1]),
                    bh, lean, 0.22 + _r.uniform(0.0, 0.18),
                    0.30 + _r.uniform(0.0, 0.22),
                    0.050 + _r.uniform(0.0, 0.022),
                    tints[_r.randrange(3)],
                )
                blade_count += 1
        else:
            ret = bmesh.ops.create_uvsphere(bm_p, u_segments=5, v_segments=3, radius=0.05 + _r.uniform(0, 0.035))
            bmesh.ops.translate(bm_p, vec=(tx, ty, 0.03), verts=ret["verts"])
    print("TUFTS_V02_BLADES", blade_count)
    finish_mesh(bm_t, colors_t, prefix + "_tufts", mat, col)
    # pebbles keep the v01 basalt flat color
    mesh_p = bpy.data.meshes.new(prefix + "_pebbles_mesh")
    bmesh.ops.recalc_face_normals(bm_p, faces=bm_p.faces)
    bm_p.to_mesh(mesh_p)
    bm_p.free()
    attr = mesh_p.color_attributes.new(name="Color", domain="CORNER", type="FLOAT_COLOR")
    for loop in mesh_p.loops:
        attr.data[loop.index].color = PAL["basalt"]
    obj_p = bpy.data.objects.new(prefix + "_pebbles", mesh_p)
    col.objects.link(obj_p)
    obj_p.data.materials.append(mat)


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
    print(f"TUFTS_V02_EXPORT {name} ({os.path.getsize(out) / 1024:.0f} KB)")


def main():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    reset_scene()
    col = bpy.data.collections.new("fol_ground_tufts_a")
    bpy.context.scene.collection.children.link(col)
    build_tufts(col)
    export_glb("fol_ground_tufts_a")
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print("TUFTS_V02_DONE")


if __name__ == "__main__":
    main()
