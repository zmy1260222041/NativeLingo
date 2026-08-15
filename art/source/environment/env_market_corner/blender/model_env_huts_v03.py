"""Phase 2 hut repair — de-pyramid the settlement roofs (art-bible v1.6 §5.3).

v03 fixes the v02 review findings:
  - v02 seeded 5/6-segment cones ("crystals") through every roof: hut A/C ridge
    spikes straddled the sail gap, hut B's roof WAS a 1.35 m hex pyramid crown
    plus five smaller pyramids, the shelter grew an amber pyramid claw out of
    its wall. Art-bible §5.3: 屋顶是朝向出入口的折片，不得随机构成尖角噪声.
  - v03 removes every roof/wall crystal. Roofs are rebuilt from the same
    shell-plate kit: hut B gains a two-course folded-plate dome with an oculus
    collar + pod finial; hut A/C get seated wind-vanes / scroll finials; the
    shelter gains end walls (with alien vent slits), a framed amber window
    mesh (own "window" family so the Godot paint rule can glow it) and roof
    tassels.

Kit modules unchanged from v02 (plinth, posts, shell plates, binds, doors,
pod windows). Z-up authored, origin at base, -Z forward after glTF Y-up
export. Do not apply scale (Blender 5.2 eats location).

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/environment/env_market_corner/blender/model_env_huts_v03.py
"""
from __future__ import annotations

import math
import os
import random as _r

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
BLEND = os.path.join(HERE, "blender/env_huts_v03.blend")
EXPORT_DIR = os.path.join(HERE, "export")
TEX_DIR = os.path.join(HERE, "textures")

PAL = {
    "coral_clay": (0xD8 / 255, 0x66 / 255, 0x5B / 255, 1.0),
    "dust_cream": (0xE7 / 255, 0xD2 / 255, 0xA3 / 255, 1.0),
    "tide_teal": (0x2F / 255, 0x8C / 255, 0x87 / 255, 1.0),
    "lichen_mint": (0x78 / 255, 0xC9 / 255, 0xA4 / 255, 1.0),
    "hearth_amber": (0xF2 / 255, 0xA8 / 255, 0x5B / 255, 1.0),
    "bark_plum": (0x5A / 255, 0x3F / 255, 0x58 / 255, 1.0),
    "silt_ink": (0x17 / 255, 0x24 / 255, 0x3B / 255, 1.0),
    "dusk_indigo": (0x34 / 255, 0x33 / 255, 0x5E / 255, 1.0),
    "basalt": (0x4B / 255, 0x52 / 255, 0x68 / 255, 1.0),
    "bone_white": (0xF5 / 255, 0xE9 / 255, 0xD2 / 255, 1.0),
}

FAM_CERAMIC = PAL["dust_cream"]
FAM_SHELL = PAL["coral_clay"]
FAM_SHELL_DARK = PAL["bark_plum"]
FAM_ALLOY = PAL["basalt"]
FAM_FIBER = PAL["dusk_indigo"]
FAM_TEAL = PAL["tide_teal"]
FAM_ORCHID = (0x9A / 255, 0x6A / 255, 0xCB / 255, 1.0)
FAM_AMBER = PAL["hearth_amber"]
CONTACT = (0.16, 0.14, 0.13, 1.0)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mat(name, color, roughness=0.85):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def scale_color(color, k):
    return (color[0] * k, color[1] * k, color[2] * k, 1.0)


def _xform(bm, verts, loc, euler=(0.0, 0.0, 0.0)):
    mat = Matrix.Translation(Vector(loc)) @ Euler(euler, "XYZ").to_matrix().to_4x4()
    bmesh.ops.transform(bm, verts=verts, matrix=mat)


def new_fam():
    return {"bm": bmesh.new(), "col": {}}


def paint(fam, verts, color):
    for vert in verts:
        fam["col"][vert] = color


def add_box(fam, size, loc, euler=(0.0, 0.0, 0.0), color=FAM_SHELL):
    bm = fam["bm"]
    ret = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=ret["verts"])
    _xform(bm, ret["verts"], loc, euler)
    paint(fam, ret["verts"], color)
    return ret["verts"]


def add_cyl(fam, r1, r2, depth, loc, segs=8, euler=(0.0, 0.0, 0.0), color=FAM_SHELL):
    bm = fam["bm"]
    ret = bmesh.ops.create_cone(
        bm, radius1=r1, radius2=r2, depth=depth, cap_ends=True, segments=segs
    )
    _xform(bm, ret["verts"], loc, euler)
    paint(fam, ret["verts"], color)
    return ret["verts"]


def add_sphere(fam, radius, loc, scale=(1.0, 1.0, 1.0), color=FAM_CERAMIC, segs=10):
    bm = fam["bm"]
    ret = bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=max(4, segs - 3), radius=radius)
    bmesh.ops.scale(bm, vec=scale, verts=ret["verts"])
    _xform(bm, ret["verts"], loc)
    paint(fam, ret["verts"], color)
    return ret["verts"]


def _island_verts(seed_vert):
    faces = set(seed_vert.link_faces)
    stack = list(seed_vert.link_faces)
    while stack:
        face = stack.pop()
        for edge in face.edges:
            for other in edge.link_faces:
                if other not in faces:
                    faces.add(other)
                    stack.append(other)
    return {vert for face in faces for vert in face.verts}


def add_shell_plate(fam, width, height, bow, thickness, loc, euler, color, segs_u=5, segs_v=3):
    """Bowed crescent plate with real thickness. Local +Y is outward bow."""
    return _add_grid_plate(fam, width, width, height, bow, thickness, loc, euler, color, segs_u, segs_v)


def add_fold_plate(fam, w0, w1, height, bow, thickness, loc, euler, color, segs_u=5, segs_v=3):
    """Trapezoid shell plate (w0 at base row, w1 at top row) for dome courses."""
    return _add_grid_plate(fam, w0, w1, height, bow, thickness, loc, euler, color, segs_u, segs_v)


def _add_grid_plate(fam, w0, w1, height, bow, thickness, loc, euler, color, segs_u, segs_v):
    bm = fam["bm"]
    grid = []
    for iv in range(segs_v + 1):
        row = []
        v = iv / segs_v
        width = w0 + (w1 - w0) * v
        for iu in range(segs_u + 1):
            u = iu / segs_u
            x = (u - 0.5) * width
            z = (v - 0.5) * height
            y = bow * math.sin(u * math.pi) * (0.35 + 0.65 * math.sin(v * math.pi))
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    faces = []
    for iv in range(segs_v):
        for iu in range(segs_u):
            faces.append(
                bm.faces.new(
                    (grid[iv][iu], grid[iv][iu + 1], grid[iv + 1][iu + 1], grid[iv + 1][iu])
                )
            )
    bmesh.ops.solidify(bm, geom=list(faces), thickness=thickness)
    plate_verts = _island_verts(grid[0][0])
    _xform(bm, list(plate_verts), loc, euler)
    paint(fam, plate_verts, color)
    return list(plate_verts)


def add_pod_lip(fam, radius, tube, loc, euler, color, segs=10):
    bm = fam["bm"]
    ret = bmesh.ops.create_cone(
        bm, radius1=radius, radius2=radius * 0.72, depth=tube, cap_ends=False, segments=segs
    )
    bmesh.ops.scale(bm, vec=(1.0, 0.55, 1.15), verts=ret["verts"])
    _xform(bm, ret["verts"], loc, euler)
    paint(fam, ret["verts"], color)
    return ret["verts"]


def link_mesh(mesh, name, mat, collection):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    return obj


def assign_box_uv(mesh, scale=0.45):
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
            uv.data[li].uv = (u * scale, v * scale)


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
    assign_box_uv(mesh)
    return link_mesh(mesh, name, mat, collection)


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


def add_bind(fam, loc, euler=(math.pi / 2, 0.0, 0.0), color=FAM_FIBER):
    add_cyl(fam, 0.018, 0.018, 0.07, loc, segs=6, euler=euler, color=color)
    add_cyl(fam, 0.028, 0.022, 0.03, loc, segs=6, euler=euler, color=scale_color(color, 1.15))


def add_wind_vane(fam, clay, loc, lod):
    """Seated wind-vane: ceramic collar + pole + two folded mini-plates + tassel.

    Replaces the v02 ridge crystals (art-bible: 折片兼作风向标，不做尖角噪声).
    """
    z = loc[2]
    add_cyl(clay, 0.095, 0.115, 0.07, (loc[0], loc[1], z + 0.035), segs=8, color=FAM_CERAMIC)
    add_cyl(fam, 0.02, 0.016, 0.42, (loc[0], loc[1], z + 0.24), segs=6, color=scale_color(FAM_SHELL_DARK, 0.9))
    add_bind(fam, (loc[0], loc[1], z + 0.30), (0, 0, 0.35))
    top = z + 0.45
    if lod == 0:
        add_fold_plate(
            fam, 0.30, 0.20, 0.17, 0.045, 0.016,
            (loc[0] + 0.13, loc[1] + 0.02, top + 0.06), (0.28, 0.0, 0.30),
            scale_color(FAM_SHELL, 1.12), segs_u=3, segs_v=2,
        )
        add_fold_plate(
            fam, 0.24, 0.16, 0.14, 0.045, 0.016,
            (loc[0] - 0.11, loc[1] - 0.02, top - 0.02), (-0.22, 0.0, -0.55 + math.pi),
            FAM_TEAL, segs_u=3, segs_v=2,
        )
        add_sphere(fam, 0.035, (loc[0], loc[1], top + 0.17), color=FAM_AMBER, segs=8)


def add_knob(fam, clay, loc, scale_k=1.0):
    """Seated ceramic knob finial — no spike."""
    add_cyl(clay, 0.075 * scale_k, 0.05 * scale_k, 0.09 * scale_k, (loc[0], loc[1], loc[2] + 0.045 * scale_k), segs=8,
            color=FAM_CERAMIC)
    add_sphere(clay, 0.065 * scale_k, (loc[0], loc[1], loc[2] + 0.11 * scale_k), scale=(1.0, 1.0, 0.85),
               color=scale_color(FAM_CERAMIC, 1.06), segs=8)


# --------------------------------------------------------------------------- hut A
def build_hut_a(col, lod, mats, stem="hut_a"):
    """Rectangular 3-bay shell-plate house. Door faces -Y (preview / approach)."""
    p = f"lod{lod}__{stem}"
    shell, clay, alloy = new_fam(), new_fam(), new_fam()
    rng = _r.Random(17 + lod)

    w, d = 4.35, 3.45
    plinth_h = 0.28
    post_h = 2.58
    wall_y = d / 2
    wall_x = w / 2
    door_w, door_h = 1.12, 1.86
    sheath_c = (0.24, 0.17, 0.21, 1.0)
    post_c = FAM_SHELL_DARK

    add_box(clay, (w + 0.38, d + 0.38, plinth_h), (0, 0, plinth_h / 2), color=FAM_CERAMIC)
    add_box(clay, (w + 0.58, d + 0.58, 0.07), (0, 0, 0.035), color=scale_color(FAM_CERAMIC, 0.88))
    add_box(shell, (w + 0.70, d + 0.70, 0.03), (0, 0, 0.014), color=CONTACT)

    post_inset = 0.14
    for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        add_box(
            shell,
            (0.18, 0.18, post_h),
            (sx * (wall_x - post_inset), sy * (wall_y - post_inset), plinth_h + post_h / 2),
            color=post_c,
        )
    if lod <= 1:
        add_box(shell, (w - 0.16, 0.14, 0.14), (0, wall_y - post_inset, plinth_h + post_h - 0.07), color=post_c)
        add_box(shell, (w - 0.16, 0.14, 0.14), (0, -wall_y + post_inset, plinth_h + post_h - 0.07), color=post_c)
        add_box(shell, (0.14, d - 0.16, 0.14), (wall_x - post_inset, 0, plinth_h + post_h - 0.07), color=post_c)
        add_box(shell, (0.14, d - 0.16, 0.14), (-wall_x + post_inset, 0, plinth_h + post_h - 0.07), color=post_c)

    sheath_h = post_h - 0.10
    add_box(shell, (w - 0.30, 0.045, sheath_h), (0, wall_y - 0.11, plinth_h + 0.04 + sheath_h / 2), color=sheath_c)
    add_box(shell, (w - 0.30, 0.045, sheath_h), (0, -wall_y + 0.11, plinth_h + 0.04 + sheath_h / 2), color=sheath_c)
    add_box(shell, (0.045, d - 0.30, sheath_h), (wall_x - 0.11, 0, plinth_h + 0.04 + sheath_h / 2), color=sheath_c)
    add_box(shell, (0.045, d - 0.30, sheath_h), (-wall_x + 0.11, 0, plinth_h + 0.04 + sheath_h / 2), color=sheath_c)

    courses = 3 if lod == 0 else (2 if lod == 1 else 1)
    course_h = (post_h - 0.12) / courses
    plate_thick = 0.055 if lod == 0 else 0.07
    bow = 0.09 if lod == 0 else 0.05

    def plate_spans(length, hole=0.0, hole_at=0.0, seed=0):
        rng.seed(seed)
        max_w = 1.28 if lod == 0 else 2.4
        if hole > 0:
            spans = [(-length / 2, hole_at - hole / 2), (hole_at + hole / 2, length / 2)]
        else:
            spans = [(-length / 2, length / 2)]
        runs = []
        for a, b in spans:
            x = a
            stagger = 0.18 if seed % 2 else 0.0
            if stagger and b - a > stagger + 0.4:
                runs.append((x, x + stagger))
                x += stagger + 0.03
            while b - x > 0.16:
                seg = min(max_w, b - x, 0.62 + rng.random() * 0.58)
                runs.append((x, x + seg))
                x += seg + 0.032
        return runs

    def plate_color(course, jitter):
        return scale_color(FAM_SHELL, (1.0 - 0.10 * course) * jitter)

    def place_long(y_sign, spans, z0, course):
        y = y_sign * (wall_y + 0.01 + 0.012 * course)
        euler = (0.0, 0.0, 0.0 if y_sign > 0 else math.pi)
        for x0, x1 in spans:
            pw = x1 - x0 - 0.03
            if pw < 0.18:
                continue
            cx = (x0 + x1) / 2
            jitter = 0.90 + rng.random() * 0.16
            add_shell_plate(
                shell, pw, course_h - 0.04, bow, plate_thick,
                (cx, y, z0 + course_h / 2), euler, plate_color(course, jitter),
                segs_u=4 if lod == 0 else 2, segs_v=2 if lod == 0 else 1,
            )
            if lod == 0 and pw > 0.55:
                add_bind(shell, (x0 + 0.06, y + y_sign * 0.04, z0 + course_h - 0.06))
                add_bind(shell, (x1 - 0.06, y + y_sign * 0.04, z0 + 0.06))

    def place_sides(x_sign, spans, z0, course):
        x = x_sign * (wall_x + 0.01 + 0.012 * course)
        euler = (0.0, 0.0, -math.pi / 2 if x_sign > 0 else math.pi / 2)
        for y0, y1 in spans:
            pw = y1 - y0 - 0.03
            if pw < 0.18:
                continue
            cy = (y0 + y1) / 2
            jitter = 0.90 + rng.random() * 0.16
            add_shell_plate(
                shell, pw, course_h - 0.04, bow, plate_thick,
                (x, cy, z0 + course_h / 2), euler, plate_color(course, jitter),
                segs_u=4 if lod == 0 else 2, segs_v=2 if lod == 0 else 1,
            )

    for c in range(courses):
        z0 = plinth_h + 0.05 + c * course_h
        door_cut = door_w + 0.10 if c < 2 else 0.0
        win_cut = 0.72 if c == 1 else 0.0
        place_long(-1, plate_spans(w - 0.28, door_cut, 0.0, 11 + c), z0, c)
        place_long(1, plate_spans(w - 0.28, 0.0, 0.0, 41 + c), z0, c)
        place_sides(-1, plate_spans(d - 0.28, 0.0, 0.0, 61 + c), z0, c)
        place_sides(1, plate_spans(d - 0.28, win_cut, 0.85, 81 + c), z0, c)

    if lod <= 1:
        jamb_d = 0.32
        jamb_z = plinth_h + 0.02
        fy = -wall_y
        add_box(shell, (0.14, jamb_d, door_h + 0.16), (-door_w / 2 - 0.07, fy + 0.08, jamb_z + (door_h + 0.16) / 2), color=post_c)
        add_box(shell, (0.14, jamb_d, door_h + 0.16), (door_w / 2 + 0.07, fy + 0.08, jamb_z + (door_h + 0.16) / 2), color=post_c)
        add_box(shell, (door_w + 0.42, jamb_d, 0.16), (0, fy + 0.08, jamb_z + door_h + 0.14), color=post_c)
        add_box(shell, (door_w - 0.04, 0.05, door_h), (0, fy + 0.24, jamb_z + door_h / 2), color=(0.20, 0.16, 0.15, 1.0))
        if lod == 0:
            add_box(
                shell, (door_w - 0.10, 0.05, door_h - 0.08),
                (-0.12, fy + 0.16, jamb_z + door_h / 2),
                (0.0, 0.42, 0.0),
                color=scale_color(FAM_SHELL, 0.82),
            )
        add_box(clay, (door_w + 0.28, 0.58, 0.07), (0, fy - 0.16, plinth_h + 0.01), color=scale_color(FAM_CERAMIC, 0.96))
        add_box(clay, (door_w + 0.10, 0.22, 0.03), (0, fy - 0.28, plinth_h + 0.045), color=scale_color(FAM_CERAMIC, 1.04))
        add_pod_lip(
            clay, 0.38, 0.12,
            (wall_x + 0.05, 0.85, plinth_h + 1.08),
            (0.0, math.pi / 2, 0.0),
            FAM_CERAMIC,
            segs=10 if lod == 0 else 8,
        )
        add_box(shell, (0.04, 0.42, 0.50), (wall_x - 0.03, 0.85, plinth_h + 1.08), color=(0.18, 0.15, 0.14, 1.0))

    if lod == 0:
        add_box(alloy, (0.58, 0.045, 0.44), (0.85, -wall_y - 0.055, plinth_h + 0.78), color=FAM_ALLOY)
        for dx, dz in ((-0.22, 0.15), (0.22, 0.15), (-0.22, -0.15), (0.22, -0.15)):
            add_cyl(
                alloy, 0.018, 0.018, 0.03,
                (0.85 + dx, -wall_y - 0.08, plinth_h + 0.78 + dz),
                segs=6, euler=(math.pi / 2, 0, 0), color=(0.62, 0.65, 0.74, 1.0),
            )

    wall_top = plinth_h + post_h
    # cornice seated on the wall head — closes the eave cavity
    add_box(shell, (w + 0.22, d + 0.22, 0.16), (0, 0, wall_top + 0.04), color=post_c)
    add_box(shell, (w + 0.48, d + 0.48, 0.08), (0, 0, wall_top + 0.12), color=scale_color(FAM_SHELL_DARK, 0.88))
    # gable plugs so the wall top is not an open attic
    add_box(shell, (0.10, d - 0.20, 0.72), (-w / 2 + 0.08, 0, wall_top + 0.42), color=post_c)
    add_box(shell, (0.10, d - 0.20, 0.72), (w / 2 - 0.08, 0, wall_top + 0.42), color=post_c)
    roof_lo = FAM_SHELL_DARK
    roof_hi = scale_color(FAM_SHELL_DARK, 1.18)
    add_shell_plate(
        shell, w + 0.85, 1.55, 0.12, 0.08,
        (0.0, -0.58, wall_top + 0.52), (-0.48, 0.0, 0.0), roof_lo,
        segs_u=5 if lod == 0 else 3, segs_v=3 if lod == 0 else 2,
    )
    add_shell_plate(
        shell, w + 0.85, 1.55, 0.12, 0.08,
        (0.0, 0.58, wall_top + 0.52), (0.48, 0.0, 0.0), roof_hi,
        segs_u=5 if lod == 0 else 3, segs_v=3 if lod == 0 else 2,
    )
    # ridge beam seals the sail gap; v03 ridge furniture is SEATED, not spiked
    ridge_z = wall_top + 1.12
    add_cyl(shell, 0.055, 0.055, w + 0.35, (0, 0, ridge_z), segs=6, euler=(0, math.pi / 2, 0),
            color=scale_color(FAM_SHELL_DARK, 0.8))
    add_cyl(clay, 0.14, 0.18, 0.28, (-1.15, 0.12, ridge_z - 0.04), segs=8, color=FAM_CERAMIC)
    add_cyl(clay, 0.0, 0.20, 0.09, (-1.15, 0.12, ridge_z + 0.10), segs=8, color=scale_color(FAM_CERAMIC, 0.85))
    add_bind(shell, (1.3, 0.0, ridge_z - 0.02), (0, math.pi / 2, 0))
    add_bind(shell, (-1.3, 0.0, ridge_z - 0.02), (0, math.pi / 2, 0))
    # wind-vane on the ridge gap centre (y=0 — clear of both sail plates),
    # knob finials seated on the gable plugs
    add_wind_vane(shell, clay, (0.62, 0.0, ridge_z + 0.04), lod)
    if lod == 0:
        add_knob(shell, clay, (-w / 2 + 0.08, 0.0, wall_top + 0.78), 1.0)
        add_knob(shell, clay, (w / 2 - 0.08, 0.0, wall_top + 0.78), 1.0)

    finish_family(shell, p + "_shell", FAM_SHELL, mats["shell"], col)
    finish_family(clay, p + "_clay", FAM_CERAMIC, mats["clay"], col)
    finish_family(alloy, p + "_alloy", FAM_ALLOY, mats["alloy"], col)


# --------------------------------------------------------------------------- hut B
def build_hut_b(col, lod, mats):
    """Six-bay wrap of the plate kit. Door faces -Y.

    v03: the v02 hex-pyramid crystal crown is replaced by a two-course
    folded-plate dome seated on the ring beam, capped with an oculus collar
    and a pod finial (no spikes anywhere on the roof).
    """
    p = f"lod{lod}__hut_b"
    shell, clay, alloy = new_fam(), new_fam(), new_fam()
    rng = _r.Random(29 + lod)
    r = 2.12
    plinth_h = 0.26
    post_h = 2.42
    bays = 6
    door_w, door_h = 1.02, 1.78
    sheath_c = (0.24, 0.17, 0.21, 1.0)
    post_c = FAM_SHELL_DARK

    add_cyl(clay, r + 0.18, r + 0.28, plinth_h, (0, 0, plinth_h / 2), segs=8, color=FAM_CERAMIC)
    add_cyl(shell, r + 0.36, r + 0.36, 0.03, (0, 0, 0.015), segs=8, color=CONTACT)
    add_cyl(shell, r - 0.10, r - 0.04, post_h - 0.04, (0, 0, plinth_h + 0.04 + (post_h - 0.04) / 2), segs=8, color=sheath_c)

    for i in range(bays):
        a = math.tau * i / bays + math.pi / 12
        add_box(
            shell, (0.16, 0.16, post_h),
            (math.cos(a) * (r - 0.10), math.sin(a) * (r - 0.10), plinth_h + post_h / 2),
            (0, 0, a), color=post_c,
        )

    courses = 3 if lod == 0 else (2 if lod == 1 else 1)
    course_h = (post_h - 0.10) / courses
    chord = 2.0 * r * math.sin(math.pi / bays) - 0.10

    def _ang_diff(a, target):
        return abs((a - target + math.pi) % math.tau - math.pi)

    door_bay = min(
        range(bays),
        key=lambda i: _ang_diff(math.tau * (i + 0.5) / bays + math.pi / 12, -math.pi / 2),
    )

    for c in range(courses):
        z0 = plinth_h + 0.05 + c * course_h
        course_shade = 1.0 - 0.10 * c
        for i in range(bays):
            a = math.tau * (i + 0.5) / bays + math.pi / 12
            if i == door_bay and c < 2:
                for side in (-1, 1):
                    aa = a + side * 0.24
                    loc = (math.cos(aa) * (r + 0.03 + 0.01 * c), math.sin(aa) * (r + 0.03 + 0.01 * c), z0 + course_h / 2)
                    add_shell_plate(
                        shell, chord * 0.30, course_h - 0.05, 0.07, 0.05,
                        loc, (0, 0, aa + math.pi / 2),
                        scale_color(FAM_TEAL, course_shade * (0.90 + rng.random() * 0.12)),
                        segs_u=3, segs_v=2 if lod == 0 else 1,
                    )
                continue
            for part, offset in ((0.46, -0.22), (0.46, 0.22)) if lod == 0 else ((0.92, 0.0),):
                aa = a + offset * 0.35
                loc = (math.cos(aa) * (r + 0.03 + 0.012 * c), math.sin(aa) * (r + 0.03 + 0.012 * c), z0 + course_h / 2)
                add_shell_plate(
                    shell, chord * part, course_h - 0.04, 0.09 if lod == 0 else 0.06, 0.055,
                    loc, (0, 0, aa + math.pi / 2),
                    scale_color(FAM_TEAL, course_shade * (0.88 + rng.random() * 0.16)),
                    segs_u=3 if lod == 0 else 2, segs_v=2 if lod == 0 else 1,
                )
            if lod == 0:
                add_bind(
                    shell,
                    (math.cos(a) * (r + 0.07), math.sin(a) * (r + 0.07), z0 + course_h - 0.05),
                    (math.pi / 2, 0, a),
                )

    if lod <= 1:
        door_a = math.tau * (door_bay + 0.5) / bays + math.pi / 12
        fx, fy = math.cos(door_a) * r, math.sin(door_a) * r
        add_box(shell, (0.13, 0.30, door_h + 0.14), (fx - math.cos(door_a + math.pi / 2) * 0.52, fy - math.sin(door_a + math.pi / 2) * 0.52, plinth_h + (door_h + 0.14) / 2), (0, 0, door_a), color=post_c)
        add_box(shell, (0.13, 0.30, door_h + 0.14), (fx + math.cos(door_a + math.pi / 2) * 0.52, fy + math.sin(door_a + math.pi / 2) * 0.52, plinth_h + (door_h + 0.14) / 2), (0, 0, door_a), color=post_c)
        add_box(shell, (door_w + 0.36, 0.30, 0.14), (fx, fy, plinth_h + door_h + 0.12), (0, 0, door_a), color=post_c)
        add_box(shell, (door_w - 0.06, 0.05, door_h), (fx * 0.90, fy * 0.90, plinth_h + door_h / 2), (0, 0, door_a), color=(0.20, 0.16, 0.15, 1.0))
        add_box(clay, (door_w + 0.22, 0.50, 0.07), (fx * 1.10, fy * 1.10, plinth_h + 0.02), (0, 0, door_a), color=scale_color(FAM_CERAMIC, 0.95))
        if lod == 0:
            win_a = door_a + math.tau / 3
            add_pod_lip(
                clay, 0.32, 0.10,
                (math.cos(win_a) * (r + 0.05), math.sin(win_a) * (r + 0.05), plinth_h + 1.15),
                (0, 0, win_a + math.pi / 2), FAM_CERAMIC,
            )
            patch_a = door_a - math.tau / 3
            add_box(
                alloy, (0.48, 0.045, 0.38),
                (math.cos(patch_a) * (r + 0.06), math.sin(patch_a) * (r + 0.06), plinth_h + 0.85),
                (0, 0, patch_a), color=FAM_ALLOY,
            )

    wall_top = plinth_h + post_h
    add_cyl(shell, r + 0.06, r + 0.20, 0.16, (0, 0, wall_top + 0.06), segs=8, color=post_c)
    add_cyl(shell, r - 0.04, r + 0.10, 0.08, (0, 0, wall_top + 0.16), segs=8, color=scale_color(FAM_SHELL_DARK, 0.9))

    # ---- folded-plate dome (v03): two shingled courses of trapezoid plates ----
    # geometry: plates lean inward from the ring beam to a small oculus ring;
    # every value derived from r/apex so nothing floats or pierces.
    ring_z = wall_top + 0.20
    apex_z = wall_top + 1.42
    r_base = r + 0.16
    r_oculus = 0.42
    slope = math.hypot(r_base - r_oculus, apex_z - ring_z)
    tilt = math.atan2(r_base - r_oculus, apex_z - ring_z)

    def dome_course(r_out, r_in, z_lo, z_hi, shade, tag):
        """One ring of 6 trapezoid plates from radius r_out@z_lo to r_in@z_hi."""
        mid_r = (r_out + r_in) / 2.0
        mid_z = (z_lo + z_hi) / 2.0
        length = math.hypot(r_out - r_in, z_hi - z_lo)
        for i in range(bays):
            a = math.tau * (i + 0.5) / bays + math.pi / 12
            w_out = 2.0 * r_out * math.sin(math.pi / bays) - 0.06
            w_in = 2.0 * r_in * math.sin(math.pi / bays) - 0.02
            loc = (math.cos(a) * mid_r, math.sin(a) * mid_r, mid_z)
            add_fold_plate(
                shell, w_out, w_in, length, 0.10 if lod == 0 else 0.04, 0.06,
                loc, (tilt, 0.0, a + math.pi / 2),
                scale_color(FAM_TEAL, shade * (0.9 + rng.random() * 0.14)),
                segs_u=3, segs_v=2 if lod == 0 else 1,
            )
            _ = tag

    split = 0.58
    r_mid = r_base - (r_base - r_oculus) * split
    z_mid = ring_z + (apex_z - ring_z) * split
    dome_course(r_base, r_mid, ring_z, z_mid + 0.06, 1.0, "lower")
    dome_course(r_mid - 0.04, r_oculus, z_mid, apex_z, 0.86, "upper")
    if lod == 0:
        for i in (1, 4):
            a = math.tau * (i + 0.5) / bays + math.pi / 12
            add_bind(
                shell,
                (math.cos(a) * (r_base + 0.05), math.sin(a) * (r_base + 0.05), ring_z + 0.10),
                (math.pi / 2, 0, a),
            )

    # oculus collar + pod finial — seated, rounded, no spike
    add_cyl(clay, 0.34, 0.40, 0.12, (0, 0, apex_z + 0.04), segs=8, color=FAM_CERAMIC)
    add_cyl(shell, 0.30, 0.30, 0.05, (0, 0, apex_z + 0.12), segs=8, color=scale_color(FAM_SHELL_DARK, 0.9))
    add_sphere(clay, 0.15, (0, 0, apex_z + 0.30), scale=(1.0, 1.0, 0.9), color=scale_color(FAM_CERAMIC, 1.05), segs=10)
    if lod == 0:
        add_bind(shell, (0.0, 0.38, apex_z + 0.06), (math.pi / 2, 0, 0))
        add_bind(shell, (0.38, -0.1, apex_z + 0.06), (math.pi / 2, 0, -0.3))

    finish_family(shell, p + "_shell", FAM_SHELL, mats["shell"], col)
    finish_family(clay, p + "_clay", FAM_CERAMIC, mats["clay"], col)
    finish_family(alloy, p + "_alloy", FAM_ALLOY, mats["alloy"], col)


# --------------------------------------------------------------------------- hut C
def build_hut_c(col, lod, mats):
    """Tall pod house: D-plan, three-finger windows, sail roof + scroll finial."""
    p = f"lod{lod}__hut_c"
    shell, clay, alloy = new_fam(), new_fam(), new_fam()
    w, d, plinth_h, post_h = 3.15, 4.15, 0.26, 3.15
    wall_y, wall_x = d / 2, w / 2
    post_c = FAM_SHELL_DARK
    add_box(clay, (w + 0.3, d + 0.3, plinth_h), (0, 0.2, plinth_h / 2), color=FAM_CERAMIC)
    add_box(shell, (w + 0.45, d + 0.45, 0.03), (0, 0.2, 0.014), color=CONTACT)
    add_box(shell, (w - 0.25, 0.045, post_h - 0.12), (0, wall_y - 0.1, plinth_h + post_h / 2), color=(0.24, 0.17, 0.21, 1.0))
    add_box(shell, (w - 0.25, 0.045, post_h - 0.12), (0, -wall_y + 0.1, plinth_h + post_h / 2), color=(0.24, 0.17, 0.21, 1.0))
    courses = 3 if lod == 0 else 2
    ch = (post_h - 0.12) / courses
    for c in range(courses):
        z0 = plinth_h + 0.04 + c * ch
        add_shell_plate(
            shell, w - 0.35, ch - 0.05, 0.16, 0.055,
            (0, -wall_y - 0.02, z0 + ch / 2), (0, 0, math.pi),
            scale_color(FAM_SHELL_DARK, 1.0 - 0.1 * c), segs_u=4, segs_v=2,
        )
        add_shell_plate(
            shell, w - 0.35, ch - 0.05, 0.10, 0.055,
            (0, wall_y + 0.02, z0 + ch / 2), (0, 0, 0),
            scale_color(FAM_ORCHID, 0.9 - 0.08 * c), segs_u=4, segs_v=2,
        )
        for sx in (-1, 1):
            add_shell_plate(
                shell, d - 0.5, ch - 0.05, 0.12, 0.055,
                (sx * (wall_x + 0.02), 0.15, z0 + ch / 2), (0, 0, -sx * math.pi / 2),
                scale_color(FAM_SHELL_DARK, 0.94 - 0.08 * c), segs_u=4, segs_v=2,
            )
    # three-finger pod windows
    if lod <= 1:
        for dx, zh in ((-0.42, 1.55), (0.0, 1.85), (0.42, 1.55)):
            add_pod_lip(clay, 0.22, 0.10, (dx, -wall_y - 0.03, plinth_h + zh), (0, 0, math.pi), FAM_TEAL, segs=8)
        add_box(shell, (0.9, 0.26, 1.7), (0, -wall_y + 0.08, plinth_h + 0.95), color=post_c)
        add_box(shell, (0.72, 0.05, 1.5), (0, -wall_y + 0.18, plinth_h + 0.9), color=(0.18, 0.15, 0.14, 1.0))
    wall_top = plinth_h + post_h
    add_box(shell, (w + 0.2, d + 0.2, 0.12), (0, 0.1, wall_top + 0.04), color=post_c)
    sail_loc = (0.0, -0.35, wall_top + 0.48)
    sail_euler = (-0.55, 0.08, 0.0)
    sail_h = 1.35
    add_shell_plate(
        shell, w + 0.4, sail_h, 0.18, 0.07,
        sail_loc, sail_euler, FAM_SHELL_DARK, segs_u=4, segs_v=2,
    )
    # v03: scroll finial seated on the sail's TOP edge (derived from the same
    # transform that placed the plate, so it cannot pierce the roof)
    top_edge = Vector(sail_loc) + Euler(sail_euler, "XYZ").to_matrix() @ Vector((0.0, 0.0, sail_h / 2))
    add_cyl(clay, 0.08, 0.10, 0.09, (top_edge.x, top_edge.y, top_edge.z - 0.02), segs=8, color=FAM_CERAMIC)
    if lod == 0:
        add_fold_plate(
            shell, 0.26, 0.16, 0.15, 0.09, 0.016,
            (top_edge.x, top_edge.y, top_edge.z + 0.10), (0.0, 0.12, math.pi / 2),
            scale_color(FAM_ORCHID, 1.0), segs_u=3, segs_v=2,
        )
        add_bind(shell, (top_edge.x, top_edge.y, top_edge.z + 0.03), (0, 0, 0.9))
        add_knob(shell, clay, (top_edge.x - 1.2, top_edge.y + 0.22, wall_top + 0.72), 0.9)
        add_knob(shell, clay, (top_edge.x + 1.2, top_edge.y + 0.22, wall_top + 0.72), 0.9)
    add_box(alloy, (0.4, 0.05, 0.32), (wall_x + 0.04, 0.6, plinth_h + 1.1), color=FAM_ALLOY)
    finish_family(shell, p + "_shell", FAM_SHELL, mats["shell"], col)
    finish_family(clay, p + "_clay", FAM_CERAMIC, mats["clay"], col)
    finish_family(alloy, p + "_alloy", FAM_ALLOY, mats["alloy"], col)


# --------------------------------------------------------------------------- shelter
def build_shelter(col, lod, mats):
    """Low crescent refuge: closed walls on all four sides (v03), framed amber
    window instead of the v02 wall crystal, seated tassels instead of roof
    crystals."""
    p = f"lod{lod}__shelter"
    shell, clay, alloy, glass = new_fam(), new_fam(), new_fam(), new_fam()
    w, d, plinth_h, post_h = 5.4, 2.85, 0.24, 2.15
    wall_y, wall_x = d / 2, w / 2
    post_c = FAM_SHELL_DARK
    add_box(clay, (w + 0.4, d + 0.35, plinth_h), (0, 0.15, plinth_h / 2), color=FAM_CERAMIC)
    add_box(shell, (w + 0.55, d + 0.5, 0.03), (0, 0.15, 0.014), color=CONTACT)
    add_box(shell, (w - 0.2, 0.05, post_h - 0.1), (0, wall_y - 0.08, plinth_h + post_h / 2), color=(0.24, 0.17, 0.21, 1.0))
    add_box(shell, (w - 0.2, 0.05, post_h - 0.1), (0, -wall_y + 0.08, plinth_h + post_h / 2), color=(0.24, 0.17, 0.21, 1.0))
    courses = 2 if lod == 0 else 1
    ch = (post_h - 0.1) / courses
    for c in range(courses):
        z0 = plinth_h + 0.05 + c * ch
        for x0, x1 in ((-w / 2 + 0.2, -0.7), (0.7, w / 2 - 0.2)):
            add_shell_plate(
                shell, x1 - x0 - 0.04, ch - 0.05, 0.14, 0.06,
                ((x0 + x1) / 2, -wall_y - 0.02, z0 + ch / 2), (0, 0, math.pi),
                scale_color(FAM_CERAMIC, 1.0 - 0.08 * c), segs_u=4, segs_v=2,
            )
        add_shell_plate(
            shell, w - 0.4, ch - 0.05, 0.10, 0.06,
            (0, wall_y + 0.02, z0 + ch / 2), (0, 0, 0),
            scale_color(FAM_CERAMIC, 0.92 - 0.08 * c), segs_u=5, segs_v=2,
        )
    # ---- v03 end walls: the shelter is no longer an open-ended shed ----
    for sx in (-1, 1):
        for c in range(courses):
            z0 = plinth_h + 0.05 + c * ch
            add_shell_plate(
                shell, d - 0.34, ch - 0.05, 0.11, 0.055,
                (sx * (wall_x - 0.02), 0.15, z0 + ch / 2), (0, 0, -sx * math.pi / 2),
                scale_color(FAM_CERAMIC, 0.96 - 0.08 * c), segs_u=4, segs_v=2,
            )
        if sx > 0 and lod == 0:
            # alien vent slit between the courses (§5.3 异星开口：气窗)
            vz = plinth_h + 0.05 + ch - 0.02
            for i in range(3):
                add_box(
                    alloy, (0.05, 0.46, 0.035),
                    (wall_x - 0.02, 0.15 + (i - 1) * 0.17, vz),
                    color=scale_color(FAM_ALLOY, 1.1),
                )
    # ---- v03 framed amber window on the back wall (replaces the crystal claw).
    # Own "window" mesh family so the Godot paint rule can glow JUST the glass.
    win_cx, win_cz = 1.05, plinth_h + 1.18
    if lod <= 1:
        add_box(shell, (1.06, 0.08, 0.80), (win_cx, wall_y - 0.02, win_cz), color=post_c)  # frame back-plate
        add_box(glass, (0.78, 0.035, 0.52), (win_cx, wall_y - 0.03, win_cz), color=FAM_AMBER)
        add_box(glass, (0.05, 0.045, 0.52), (win_cx - 0.13, wall_y - 0.03, win_cz), color=scale_color(FAM_TEAL, 1.1))
        add_box(glass, (0.05, 0.045, 0.52), (win_cx + 0.13, wall_y - 0.03, win_cz), color=scale_color(FAM_TEAL, 1.1))
        add_box(shell, (1.18, 0.10, 0.09), (win_cx, wall_y - 0.02, win_cz + 0.44), color=post_c)  # lintel
        add_box(shell, (1.18, 0.10, 0.09), (win_cx, wall_y - 0.02, win_cz - 0.44), color=post_c)  # sill
        add_box(shell, (0.09, 0.10, 0.97), (win_cx - 0.575, wall_y - 0.02, win_cz), color=post_c)
        add_box(shell, (0.09, 0.10, 0.97), (win_cx + 0.575, wall_y - 0.02, win_cz), color=post_c)
    # door bench + threshold (kept from v02)
    add_box(shell, (1.4, 0.28, 0.14), (0, -wall_y + 0.05, plinth_h + 0.22), color=post_c)
    wall_top = plinth_h + post_h
    add_box(shell, (w + 0.35, d + 0.3, 0.12), (0, 0.1, wall_top + 0.04), color=post_c)
    add_shell_plate(
        shell, w + 0.7, 1.85, 0.22, 0.08,
        (0.0, -0.15, wall_top + 0.55), (-0.72, 0.0, 0.0), FAM_SHELL_DARK,
        segs_u=5, segs_v=3,
    )
    if lod == 0:
        # seated roof tassels + a knob at the sail's high edge (no crystals)
        sail_top_z = wall_top + 0.55 + (1.85 / 2) * math.cos(0.72)
        add_knob(shell, clay, (1.9, 0.4, sail_top_z - 0.10), 0.85)
        add_bind(shell, (-2.4, -0.75, wall_top + 0.35), (math.pi / 2, 0, 0.4))
        add_bind(shell, (2.4, -0.75, wall_top + 0.35), (math.pi / 2, 0, -0.4))
        add_box(alloy, (0.34, 0.045, 0.26), (-1.4, -wall_y - 0.05, plinth_h + 0.7), color=FAM_ALLOY)
    finish_family(shell, p + "_shell", FAM_SHELL, mats["shell"], col)
    finish_family(clay, p + "_clay", FAM_CERAMIC, mats["clay"], col)
    finish_family(alloy, p + "_alloy", FAM_ALLOY, mats["alloy"], col)
    finish_family(glass, p + "_window", FAM_AMBER, mats["clay"], col)


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
    print(f"HUT_V03_EXPORT {name} ({os.path.getsize(out) / 1024:.0f} KB)")


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
    kits = {
        "env_hut_residential_a": (build_hut_a, "tex_shell_tile_1k.png", "tex_clay_tile_1k.png", FAM_SHELL, FAM_CERAMIC),
        "env_hut_residential_b": (build_hut_b, "tex_shell_teal_1k.png", "tex_clay_teal_1k.png", FAM_TEAL, (0.66, 0.77, 0.73, 1.0)),
        "env_hut_residential_c": (build_hut_c, "tex_shell_plum_1k.png", "tex_clay_amber_1k.png", FAM_SHELL_DARK, (0.86, 0.73, 0.55, 1.0)),
        "env_shelter_distant_a": (build_shelter, "tex_shell_cream_1k.png", "tex_clay_amber_1k.png", FAM_CERAMIC, FAM_AMBER),
    }
    for name, (build, shell_tex, clay_tex, shell_col, clay_col) in kits.items():
        mats = {
            "shell": make_mat("mat_%s_shell" % name, shell_col, 0.85),
            "clay": make_mat("mat_%s_clay" % name, clay_col, 0.90),
            "alloy": make_mat("mat_%s_alloy" % name, FAM_ALLOY, 0.55),
        }
        hook_image(mats["shell"], os.path.join(TEX_DIR, shell_tex), True)
        hook_image(mats["clay"], os.path.join(TEX_DIR, clay_tex), True)
        hook_image(mats["shell"], os.path.join(TEX_DIR, "tex_shell_n_1k.png"), False)
        hook_image(mats["clay"], os.path.join(TEX_DIR, "tex_clay_n_1k.png"), False)
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
        for lod in (0, 1, 2):
            build(col, lod, mats)
        tris = count_tris(col)
        print(f"HUT_V03_TRIS {name} {tris}")
        export_glb(name)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print("HUT_V03_DONE blend=%s" % BLEND)


if __name__ == "__main__":
    main()
