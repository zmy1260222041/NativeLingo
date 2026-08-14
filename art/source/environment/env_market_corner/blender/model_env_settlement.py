"""Hand-model the v1.4 settlement environment assets (art-bible §3.6/§5/§8.8).

One script, five assets — closes the baseline review FAILs (积木判定/材质家族/
地表分层/使用痕迹/密度):
  - env_hut_residential_a   rectangular hut, shell-plate walls + cast-ceramic
                           plinth + alloy patch (3 families, §5.3 minimum list)
  - env_hut_residential_b   octagonal band hut variant (non-standard variation)
  - env_ground_market_a     v2 three-layer ground: packed traffic network with
                           crescent wear at the stall, dust field, moss/pebble
                           rim band that breaks the knife-cut path edges
  - prp_crate_stack_a       stacked crates + sacks (堆货 trace, §5.5)
  - prp_drying_rack_a       fiber drying rack (晾晒 trace + NPC anchor accent)
  - prp_amphora_cluster_a   cast-ceramic vessel cluster (market density §5.2)

Same discipline as model_env_props.py: Blender Z-up authored, origin at base,
geometry at world coords, deterministic seeds, export per-collection only.
Coordinate note: game(x,z) maps to Blender(x, -z_game→y): blender +Y is game -Z.

Run headless:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/environment/env_market_corner/blender/model_env_settlement.py
"""
import bpy
import bmesh
import math
import os
import random as _r

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
BLEND = os.path.join(HERE, "blender/env_settlement.blend")
EXPORT_DIR = os.path.join(HERE, "export")

PAL = {
    "coral_clay":   (0xD8/255, 0x66/255, 0x5B/255, 1.0),
    "dust_cream":   (0xE7/255, 0xD2/255, 0xA3/255, 1.0),
    "tide_teal":    (0x2F/255, 0x8C/255, 0x87/255, 1.0),
    "lichen_mint":  (0x78/255, 0xC9/255, 0xA4/255, 1.0),
    "hearth_amber": (0xF2/255, 0xA8/255, 0x5B/255, 1.0),
    "bark_plum":    (0x5A/255, 0x3F/255, 0x58/255, 1.0),
    "silt_ink":     (0x17/255, 0x24/255, 0x3B/255, 1.0),
    "dusk_indigo":  (0x34/255, 0x33/255, 0x5E/255, 1.0),
    "basalt":       (0x4B/255, 0x52/255, 0x68/255, 1.0),
    "bone_white":   (0xF5/255, 0xE9/255, 0xD2/255, 1.0),
    "warm_apricot": (0xBF/255, 0xA9/255, 0x82/255, 1.0),
}

# Material family value ladder (§3.6 白昼可分): ceramic light → shell mid →
# alloy dark. Values are vertex-color authored so grayscale still separates.
FAM_CERAMIC = PAL["dust_cream"]
FAM_SHELL = PAL["coral_clay"]
FAM_SHELL_DARK = PAL["bark_plum"]
FAM_ALLOY = PAL["basalt"]
FAM_FIBER = PAL["dusk_indigo"]
PACKED_DIRT = (0xB5/255, 0x96/255, 0x6E/255, 1.0)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mat(name, color, roughness=0.8):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return m


def link_mesh(mesh, name, mat, collection):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    return obj


def set_vertex_color(mesh, color):
    attr = mesh.color_attributes.new(name="Color", domain='CORNER', type='FLOAT_COLOR')
    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            attr.data[loop_idx].color = (color[0], color[1], color[2], 1.0)


def set_vertex_color_per_face(mesh, face_colors):
    """face_colors: list of (poly_index, rgba)."""
    attr = mesh.color_attributes.new(name="Color", domain='CORNER', type='FLOAT_COLOR')
    for idx, color in face_colors:
        for loop_idx in mesh.polygons[idx].loop_indices:
            attr.data[loop_idx].color = (color[0], color[1], color[2], 1.0)


def scale_color(color, k):
    return (color[0] * k, color[1] * k, color[2] * k, 1.0)


def _mix(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, 1.0)


def prim_box(name, mat, collection, size, loc, rot=(0, 0, 0), vcol=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    o = link_mesh(mesh, name, mat, collection)
    o.rotation_euler = rot
    if vcol is not None:
        set_vertex_color(mesh, vcol)
    return o


def prim_cylinder(name, mat, collection, r1, r2, depth, loc, seg=12, rot=(0, 0, 0), vcol=None, smooth=False):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, radius1=r1, radius2=r2, depth=depth, cap_ends=True, segments=seg)
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    o = link_mesh(mesh, name, mat, collection)
    o.location = loc
    o.rotation_euler = rot
    if vcol is not None:
        set_vertex_color(mesh, vcol)
    return o


def prim_sphere(name, mat, collection, radius, loc, seg=12, ring=8, scale=(1, 1, 1), vcol=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=radius)
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    o = link_mesh(mesh, name, mat, collection)
    o.location = loc
    o.scale = scale
    if vcol is not None:
        set_vertex_color(mesh, vcol)
    return o


# ================================================================ hut A
def build_hut_a(col, lod):
    """DEPRECATED. Phase 1 residences are authored by model_env_huts_v02.py.
    Do not export this builder over env_hut_residential_*.glb."""
    p = f"lod{lod}__hut_a"
    shell = make_mat("mat_hut_shell", FAM_SHELL, roughness=0.85)
    ceramic = make_mat("mat_hut_ceramic", FAM_CERAMIC, roughness=0.9)
    alloy = make_mat("mat_hut_alloy", FAM_ALLOY, roughness=0.6)
    # shared color carriers: vcol decides family value, mats only keep slots distinct
    W, D, H_PLINTH = 4.3, 3.4, 0.26

    # --- cast-ceramic plinth (family 2): chamfered ring base
    pl = prim_box(p + "_plinth", ceramic, col, (W + 0.3, D + 0.3, H_PLINTH), (0, 0, H_PLINTH / 2), vcol=FAM_CERAMIC)
    prim_box(p + "_plinth_lip", ceramic, col, (W + 0.5, D + 0.5, 0.08), (0, 0, 0.04), vcol=scale_color(FAM_CERAMIC, 0.88))
    # contact skirt: dark band faking baked AO where mass meets ground (§8.8-2)
    prim_box(p + "_contact", shell, col, (W + 0.62, D + 0.62, 0.035), (0, 0, 0.0175), vcol=(0.16, 0.14, 0.13, 1.0))

    # --- corner posts + ring beam (frame reads before panels §5.3)
    post_h = 2.55
    for sx in (-1, 1):
        for sy in (-1, 1):
            prim_box(p + f"_post_{sx}{sy}", shell, col, (0.16, 0.16, post_h),
                     (sx * (W / 2 - 0.1), sy * (D / 2 - 0.1), H_PLINTH + post_h / 2),
                     vcol=FAM_SHELL_DARK)
    if lod == 0:
        prim_box(p + "_beam_x", shell, col, (W - 0.1, 0.12, 0.12), (0, D / 2 - 0.1, H_PLINTH + post_h - 0.06), vcol=FAM_SHELL_DARK)
        prim_box(p + "_beam_x2", shell, col, (W - 0.1, 0.12, 0.12), (0, -D / 2 + 0.1, H_PLINTH + post_h - 0.06), vcol=FAM_SHELL_DARK)
        prim_box(p + "_beam_y", shell, col, (0.12, D - 0.1, 0.12), (W / 2 - 0.1, 0, H_PLINTH + post_h - 0.06), vcol=FAM_SHELL_DARK)
        prim_box(p + "_beam_y2", shell, col, (0.12, D - 0.1, 0.12), (-W / 2 + 0.1, 0, H_PLINTH + post_h - 0.06), vcol=FAM_SHELL_DARK)

    # --- backing wall: dark inner sheath so every panel gap reads as a seam
    backing_vcol = (0.24, 0.17, 0.21, 1.0)
    prim_box(p + "_backing_f", shell, col, (W - 0.24, 0.04, post_h - 0.12),
             (0, D / 2 - 0.075, H_PLINTH + 0.05 + (post_h - 0.12) / 2), vcol=backing_vcol)
    prim_box(p + "_backing_b", shell, col, (W - 0.24, 0.04, post_h - 0.12),
             (0, -D / 2 + 0.075, H_PLINTH + 0.05 + (post_h - 0.12) / 2), vcol=backing_vcol)
    prim_box(p + "_backing_l", shell, col, (0.04, D - 0.24, post_h - 0.12),
             (-W / 2 + 0.075, 0, H_PLINTH + 0.05 + (post_h - 0.12) / 2), vcol=backing_vcol)
    prim_box(p + "_backing_r", shell, col, (0.04, D - 0.24, post_h - 0.12),
             (W / 2 - 0.075, 0, H_PLINTH + 0.05 + (post_h - 0.12) / 2), vcol=backing_vcol)

    # --- shell-plate walls (family 1, main ≥60%): overlapping courses with gaps
    courses = 3 if lod == 0 else 1
    course_h = (post_h - 0.1) / courses
    door_w, door_h = 1.05, 1.8
    win_side_x = W / 2
    _r.seed(31)
    for c in range(courses):
        z0 = H_PLINTH + 0.05 + c * course_h
        inset = 0.02 * c
        shade = scale_color(FAM_SHELL, 1.0 - 0.06 * c)
        # front (+Y): leave door opening in course 0/1
        front_panels = _wall_panel_runs(W - 0.3, door_w if c < 2 else 0.0, seed=11 + c, lod=lod)
        for (x0, x1) in front_panels:
            cx = x0 + (x1 - x0) / 2
            jitter = 0.92 + _r.random() * 0.16
            prim_box(p + f"_wallp_f{c}_{int(cx*100)}", shell, col,
                     (x1 - x0 - 0.05, 0.075, course_h - 0.05),
                     (cx, D / 2 - inset, z0 + course_h / 2), vcol=scale_color(shade, jitter))
        # back (-Y), sides (±X; +X carries the window in courses 0/1)
        for (x0, x1) in _wall_panel_runs(W - 0.3, 0.0, seed=41 + c, lod=lod):
            cx = x0 + (x1 - x0) / 2
            prim_box(p + f"_wallp_b{c}_{int(cx*100)}", shell, col,
                     (x1 - x0 - 0.05, 0.075, course_h - 0.05),
                     (cx, -D / 2 + inset, z0 + course_h / 2), vcol=scale_color(shade, 0.92 + _r.random() * 0.16))
        gap_x = 0.66 if c < 2 else 0.0
        for (y0, y1) in _wall_panel_runs(D - 0.3, 0.0, seed=61 + c, lod=lod):
            cy = y0 + (y1 - y0) / 2
            prim_box(p + f"_wallp_l{c}_{int(cy*100)}", shell, col,
                     (0.075, y1 - y0 - 0.05, course_h - 0.05),
                     (-win_side_x + inset, cy, z0 + course_h / 2), vcol=scale_color(shade, 0.92 + _r.random() * 0.16))
        for (y0, y1) in _wall_panel_runs(D - 0.3, gap_x, seed=81 + c, lod=lod, hole_center=0.9):
            cy = y0 + (y1 - y0) / 2
            prim_box(p + f"_wallp_r{c}_{int(cy*100)}", shell, col,
                     (0.075, y1 - y0 - 0.05, course_h - 0.05),
                     (win_side_x - inset, cy, z0 + course_h / 2), vcol=scale_color(shade, 0.92 + _r.random() * 0.16))

    if lod <= 1:
        # --- door construction (§5.3): jamb thickness + recess + ajar leaf
        dz0 = H_PLINTH + 0.03
        prim_box(p + "_door_jamb_l", shell, col, (0.12, 0.3, door_h + 0.12),
                 (-door_w / 2 - 0.06, D / 2 - 0.12, dz0 + (door_h + 0.12) / 2), vcol=scale_color(FAM_SHELL, 0.62))
        prim_box(p + "_door_jamb_r", shell, col, (0.12, 0.3, door_h + 0.12),
                 (door_w / 2 + 0.06, D / 2 - 0.12, dz0 + (door_h + 0.12) / 2), vcol=scale_color(FAM_SHELL, 0.62))
        prim_box(p + "_door_lintel", shell, col, (door_w + 0.36, 0.3, 0.14),
                 (0, D / 2 - 0.12, dz0 + door_h + 0.12), vcol=scale_color(FAM_SHELL, 0.62))
        prim_box(p + "_door_recess", shell, col, (door_w, 0.06, door_h),
                 (0, D / 2 - 0.3, dz0 + door_h / 2), vcol=(0.20, 0.16, 0.15, 1.0))
        if lod == 0:
            leaf = prim_box(p + "_door_leaf", shell, col, (door_w - 0.08, 0.05, door_h - 0.06),
                            (0, 0, 0), vcol=scale_color(FAM_SHELL, 0.9))
            leaf.location = (-door_w / 2 + 0.05, D / 2 - 0.22, dz0 + (door_h - 0.06) / 2)
            leaf.rotation_euler = (0, -0.55, 0)
            leaf.location.x += math.sin(0.55) * 0.4
        # threshold stone (ceramic family reuse at the crossing)
        prim_box(p + "_door_threshold", ceramic, col, (door_w + 0.2, 0.5, 0.07),
                 (0, D / 2 + 0.12, H_PLINTH + 0.02), vcol=scale_color(FAM_CERAMIC, 0.98))

        # --- framed window on +X (course 0/1 hole already left at y≈0.9)
        prim_box(p + "_win_frame_t", shell, col, (0.1, 0.72, 0.1),
                 (win_side_x + 0.02, 0.9, H_PLINTH + 1.32), vcol=FAM_SHELL_DARK)
        prim_box(p + "_win_frame_b", shell, col, (0.1, 0.72, 0.1),
                 (win_side_x + 0.02, 0.9, H_PLINTH + 0.62), vcol=FAM_SHELL_DARK)
        prim_box(p + "_win_frame_l", shell, col, (0.1, 0.1, 0.7),
                 (win_side_x + 0.02, 0.9 - 0.31, H_PLINTH + 0.97), vcol=FAM_SHELL_DARK)
        prim_box(p + "_win_frame_r", shell, col, (0.1, 0.1, 0.7),
                 (win_side_x + 0.02, 0.9 + 0.31, H_PLINTH + 0.97), vcol=FAM_SHELL_DARK)
        prim_box(p + "_win_dark", shell, col, (0.04, 0.56, 0.56),
                 (win_side_x - 0.02, 0.9, H_PLINTH + 0.97), vcol=(0.18, 0.15, 0.14, 1.0))

    if lod == 0:
        # --- alloy patch (family 3, 旧合金补片 repair trace §5.5)
        patch = prim_box(p + "_alloy_patch", alloy, col, (0.55, 0.05, 0.42),
                         (-W / 2 + 0.9, D / 2 + 0.045, H_PLINTH + 0.72), vcol=(0.46, 0.49, 0.58, 1.0))
        for (dx, dz) in [(-0.22, 0.16), (0.22, 0.16), (-0.22, -0.16), (0.22, -0.16)]:
            prim_cylinder(p + f"_rivet_{int(dx*100)}", alloy, col, 0.02, 0.02, 0.025,
                          (-W / 2 + 0.9 + dx, D / 2 + 0.075, H_PLINTH + 0.72 + dz), seg=6,
                          rot=(math.pi / 2, 0, 0), vcol=(0.62, 0.65, 0.74, 1.0))
        # vent pod (ceramic) for silhouette interest on the ridge
        prim_cylinder(p + "_vent", ceramic, col, 0.16, 0.2, 0.34, (-1.1, -0.4, 3.62), seg=8, vcol=FAM_CERAMIC)
        prim_cylinder(p + "_vent_cap", ceramic, col, 0.0, 0.22, 0.1, (-1.1, -0.4, 3.83), seg=8, vcol=scale_color(FAM_CERAMIC, 0.85))

    # --- roof: two-layer eave construction (叠压) — gable prisms
    roof_mat = make_mat("mat_hut_roof", FAM_SHELL, roughness=0.9)
    z_top = H_PLINTH + post_h + 0.02
    _gable_prism(col, p + "_roof_eave", roof_mat, W + 0.9, D + 0.8, 0.72, (0, 0, z_top), FAM_SHELL_DARK if lod else FAM_SHELL_DARK)
    _gable_prism(col, p + "_roof_upper", roof_mat, W + 0.2, D + 0.15, 0.62, (0, 0, z_top + 0.42), scale_color(FAM_SHELL_DARK, 1.25))
    if lod == 0:
        prim_cylinder(p + "_ridge", roof_mat, col, 0.07, 0.07, W + 0.5, (0, 0, z_top + 1.12), seg=6,
                      rot=(0, math.pi / 2, 0), vcol=scale_color(FAM_SHELL_DARK, 0.8))


def _gable_prism(col, name, mat, w, d, h, loc, vcol):
    """Triangular prism roof slab, ridge along X, Z-up authored."""
    bm = bmesh.new()
    hw, hd = w / 2, d / 2
    t = 0.09  # slab thickness under the slope faces
    low = [(-hw, -hd, 0), (hw, -hd, 0), (-hw, hd, 0), (hw, hd, 0)]
    ridge = [(-hw, 0, h), (hw, 0, h)]
    under = [(-hw, -hd, t), (hw, -hd, t), (-hw, hd, t), (hw, hd, t)]
    under_ridge = [(-hw, 0, h - t), (hw, 0, h - t)]
    verts = low + ridge + under + under_ridge
    for v in verts:
        bm.verts.new(v)
    bm.verts.ensure_lookup_table()
    faces = [
        (0, 1, 5, 4),        # south slope (+Y face)
        (2, 7, 6, 3),        # north slope
        (0, 4, 8, 2),        # south eave band
        (1, 3, 9, 5),        # north eave band
        (2, 8, 9, 3),        # bottom
        (4, 5, 9, 8),        # underside
        (0, 2, 3, 1),        # west gable
        (4, 6, 7, 5),        # east gable inner
    ]
    for f in faces:
        bm.faces.new([bm.verts[i] for i in f])
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    set_vertex_color(mesh, vcol)
    o = link_mesh(mesh, name, mat, col)
    o.location = loc
    return o


def _wall_panel_runs(length, hole_w, seed, lod, hole_center=0.0):
    """Split a wall of `length` into panel runs, leaving an optional hole
    (width hole_w centered at hole_center). 0.035 gaps between runs read as
    shell-plate seams."""
    _r.seed(seed)
    max_panel = 1.35 if lod == 0 else 2.6
    if hole_w > 0:
        hl = hole_center - hole_w / 2
        hr = hole_center + hole_w / 2
        spans = [(-length / 2, hl), (hr, length / 2)]
    else:
        spans = [(-length / 2, length / 2)]
    runs = []
    for (a, b) in spans:
        x = a
        while b - x > 0.12:
            seg = min(max_panel, b - x, 0.55 + _r.uniform(0, 0.8))
            runs.append((x, x + seg))
            x += seg + 0.035
    return runs


# ================================================================ hut B
def build_hut_b(col, lod):
    """Octagonal cast-band hut variant: ceramic plinth + 6 posts + tapering
    shell bands + stepped cone roof. Families: ceramic bands, shell frame, one
    alloy patch."""
    p = f"lod{lod}__hut_b"
    shell = make_mat("mat_hutb_shell", FAM_SHELL_DARK, roughness=0.85)
    ceramic = make_mat("mat_hutb_ceramic", FAM_CERAMIC, roughness=0.9)
    alloy = make_mat("mat_hutb_alloy", FAM_ALLOY, roughness=0.6)
    R = 2.15
    prim_cylinder(p + "_plinth", ceramic, col, R + 0.16, R + 0.26, 0.24, (0, 0, 0.12), seg=8, vcol=FAM_CERAMIC)
    prim_cylinder(p + "_contact", shell, col, R + 0.34, R + 0.34, 0.035, (0, 0, 0.0175), seg=8, vcol=(0.16, 0.14, 0.13, 1.0))
    # 6 posts
    post_h = 2.3
    for i in range(6):
        a = math.tau * i / 6 + math.pi / 8
        prim_box(p + f"_post_{i}", shell, col, (0.15, 0.15, post_h),
                 (math.cos(a) * (R - 0.12), math.sin(a) * (R - 0.12), 0.24 + post_h / 2), vcol=FAM_SHELL_DARK)
    # inner core: dark sheath visible through the band gaps (seam read, no see-through)
    prim_cylinder(p + "_core", shell, col, R - 0.12, R - 0.06, post_h - 0.02,
                  (0, 0, 0.24 + 0.05 + (post_h - 0.02) / 2 - 0.025), seg=8, vcol=(0.24, 0.17, 0.21, 1.0))
    # tapering wall bands (cast ceramic family main read via light value)
    bands = 3 if lod == 0 else 1
    band_h = (post_h - 0.05) / bands
    for b in range(bands):
        r_b = R - 0.02 - 0.075 * b
        prim_cylinder(p + f"_band_{b}", ceramic, col, r_b - 0.06, r_b, band_h - 0.045,
                      (0, 0, 0.24 + 0.05 + b * band_h + band_h / 2), seg=8, vcol=scale_color(FAM_CERAMIC, 1.0 - 0.05 * b))
    if lod <= 1:
        # door: jamb + recess + ajar leaf on +Y flat
        dw, dh = 1.0, 1.75
        prim_box(p + "_door_jamb_l", shell, col, (0.12, 0.26, dh + 0.1), (-dw / 2 - 0.06, R - 0.12, 0.24 + (dh + 0.1) / 2), vcol=FAM_SHELL_DARK)
        prim_box(p + "_door_jamb_r", shell, col, (0.12, 0.26, dh + 0.1), (dw / 2 + 0.06, R - 0.12, 0.24 + (dh + 0.1) / 2), vcol=FAM_SHELL_DARK)
        prim_box(p + "_door_lintel", shell, col, (dw + 0.34, 0.26, 0.13), (0, R - 0.12, 0.24 + dh + 0.13), vcol=FAM_SHELL_DARK)
        prim_box(p + "_door_recess", shell, col, (dw, 0.06, dh), (0, R - 0.3, 0.24 + dh / 2), vcol=(0.20, 0.16, 0.15, 1.0))
        if lod == 0:
            leaf = prim_box(p + "_door_leaf", shell, col, (dw - 0.07, 0.05, dh - 0.05), (0, 0, 0), vcol=scale_color(FAM_CERAMIC, 0.8))
            leaf.location = (-dw / 2 + 0.04, R - 0.22, 0.24 + (dh - 0.05) / 2)
            leaf.rotation_euler = (0, 0.3, 0)
            leaf.location.x += math.sin(0.3) * 0.28
        prim_box(p + "_door_threshold", ceramic, col, (dw + 0.2, 0.5, 0.07), (0, R + 0.1, 0.25), vcol=scale_color(FAM_CERAMIC, 0.8))
        if lod == 0:
            patch = prim_box(p + "_alloy_patch", alloy, col, (0.5, 0.05, 0.4),
                             (R - 0.02, -0.7, 0.9), vcol=FAM_ALLOY)
            patch.rotation_euler = (0, 0, 0)
    # stepped cone roof (shell family dark)
    roof = make_mat("mat_hutb_roof", FAM_SHELL, roughness=0.9)
    steps = 3 if lod == 0 else 1
    z = 0.24 + post_h
    radii = [(R + 0.55, 0.4), (R - 0.1, 0.38), (R - 0.7, 0.36)] if lod == 0 else [(R + 0.55, 1.1)]
    for i, (rr, hh) in enumerate(radii[:steps]):
        prim_cylinder(p + f"_roof_{i}", roof, col, rr - 0.45, rr, hh, (0, 0, z + hh / 2), seg=8,
                      vcol=scale_color(FAM_SHELL_DARK, 1.0 + 0.12 * i))
        z += hh - 0.08
    if lod == 0:
        prim_sphere(p + "_finial", roof, col, 0.14, (0, 0, z + 0.12), seg=8, ring=6, vcol=FAM_ALLOY)


# ================================================================ ground v2
def _ribbon(bm, points, widths, z, vcol_center, vcol_edge):
    """Append a wear ribbon (two triangles per segment) into bm. points are
    (x,y) in order; widths per point. Center vertices darker (packed), edges
    lighter — vertex gradient replaces the knife-cut decal edge."""
    mid = []
    for i, (px, py) in enumerate(points):
        prev = points[max(0, i - 1)]
        nxt = points[min(len(points) - 1, i + 1)]
        dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
        ln = max(1e-5, math.hypot(dx, dy))
        nx, ny = -dy / ln, dx / ln
        w = widths[i] / 2
        l = bm.verts.new((px + nx * w, py + ny * w, z))
        r = bm.verts.new((px - nx * w, py - ny * w, z))
        c = bm.verts.new((px, py, z + 0.004))
        mid.append((l, c, r))
    for i in range(len(mid) - 1):
        l0, c0, r0 = mid[i]
        l1, c1, r1 = mid[i + 1]
        bm.faces.new((l0, l1, c1, c0))
        bm.faces.new((c0, c1, r1, r0))
    # end caps
    if mid:
        l0, c0, r0 = mid[0]
        bm.faces.new((l0, c0, r0))
        l1, c1, r1 = mid[-1]
        bm.faces.new((r1, c1, l1))


def _apply_face_gradient(mesh, center_vcol, edge_vcol, base_z=0.012, center_z=0.016):
    """Center-strip faces darker (packed), edge faces lighter (dusty blend)."""
    attr = mesh.color_attributes.new(name="Color", domain='CORNER', type='FLOAT_COLOR')
    for poly in mesh.polygons:
        zs = [mesh.vertices[vi].co.z for vi in poly.vertices]
        avg_z = sum(zs) / len(zs)
        t = min(1.0, max(0.0, (avg_z - base_z) / max(1e-5, center_z - base_z)))
        col = tuple(e + (c - e) * t for c, e in zip(center_vcol[:3], edge_vcol[:3])) + (1.0,)
        for loop_idx in poly.loop_indices:
            attr.data[loop_idx].color = col


# wear-network centerlines shared by ground ribbons and tuft placement
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


def build_ground_v2(col):
    prefix = "env_ground_market_a"
    g = make_mat("mat_env_ground", PAL["dust_cream"], roughness=0.95)

    # --- layer 2: dust field (base)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(28.0, 28.0, 0.5), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, -0.25), verts=bm.verts)
    mesh = bpy.data.meshes.new(prefix + "_field_mesh")
    bm.to_mesh(mesh)
    bm.free()
    set_vertex_color(mesh, PAL["dust_cream"])
    link_mesh(mesh, prefix + "_field", g, col)

    # --- layer 1: packed traffic network (game z → blender y = -z_game)
    paths = PATHS
    bm = bmesh.new()
    bm_fade = bmesh.new()
    _r.seed(97)
    for pts in paths:
        widths = [1.15 + _r.uniform(-0.12, 0.18) for _ in pts]
        _ribbon(bm, pts, widths, 0.012, PACKED_DIRT, PAL["dust_cream"])
        fade_w = [w + 0.6 for w in widths]
        _ribbon(bm_fade, pts, fade_w, 0.0095, PACKED_DIRT, PAL["dust_cream"])
    mesh = bpy.data.meshes.new(prefix + "_paths_mesh")
    bm.to_mesh(mesh)
    bm.free()
    _apply_face_gradient(mesh, scale_color(PACKED_DIRT, 0.88), scale_color(PAL["dust_cream"], 1.04))
    link_mesh(mesh, prefix + "_paths", g, col)
    fade_mesh = bpy.data.meshes.new(prefix + "_paths_fade_mesh")
    bm_fade.to_mesh(fade_mesh)
    bm_fade.free()
    set_vertex_color(fade_mesh, _mix(PACKED_DIRT, PAL["dust_cream"], 0.55))
    link_mesh(fade_mesh, prefix + "_paths_fade", g, col)

    # crescent wear blob in front of the stall (§8.8-4: ≥2.5m readable)
    bm = bmesh.new()
    crescent = [(-2.9, 1.0), (-2.2, 1.55), (-1.8, 1.85), (-1.3, 1.9), (-0.7, 1.65), (-0.6, 1.15), (-1.0, 0.75), (-1.9, 0.7), (-2.9, 1.0)]
    _ribbon(bm, crescent, [0.5, 1.1, 1.35, 1.1, 0.9, 0.7, 0.6, 0.5, 0.4], 0.0125, PACKED_DIRT, PAL["dust_cream"])
    mesh = bpy.data.meshes.new(prefix + "_crescent_mesh")
    bm.to_mesh(mesh)
    bm.free()
    _apply_face_gradient(mesh, scale_color(PACKED_DIRT, 0.92), scale_color(PAL["dust_cream"], 1.02), 0.0125, 0.0165)
    link_mesh(mesh, prefix + "_crescent", g, col)

    # plaza wear ring around the meeting disc edge
    bm = bmesh.new()
    ring = []
    for i in range(37):
        a = math.tau * i / 36
        ring.append((math.cos(a) * 5.0, math.sin(a) * 5.0))
    _ribbon(bm, ring, [0.9] * 37, 0.0115, PACKED_DIRT, PAL["dust_cream"])
    mesh = bpy.data.meshes.new(prefix + "_plazaring_mesh")
    bm.to_mesh(mesh)
    bm.free()
    _apply_face_gradient(mesh, scale_color(PACKED_DIRT, 0.9), scale_color(PAL["dust_cream"], 1.03), 0.0115, 0.0155)
    link_mesh(mesh, prefix + "_plazaring", g, col)

    # drain grate keeps its post (utility trace from v1)
    grate = prim_box(prefix + "_grate", g, col, (1.2, 0.8, 0.04), (3.0, -4.0, 0.02), vcol=PAL["silt_ink"])


def build_tufts(col):
    """fol_ground_tufts_a — layer-3 moss/rock rim band (separate asset so the
    ground GLB keeps its Gate E 'top surface at y≈0' contract)."""
    g = make_mat("mat_fol_tufts", PAL["tide_teal"], roughness=0.95)
    prefix = "fol_ground_tufts_a"
    paths = PATHS
    bm_t = bmesh.new()
    bm_p = bmesh.new()
    _r.seed(5)
    edge_spots = []
    for i in range(64):
        a = math.tau * i / 64 + _r.uniform(-0.05, 0.05)
        r = 12.6 + _r.uniform(-0.6, 1.6)
        edge_spots.append((math.cos(a) * r, math.sin(a) * r))
    for pts in paths:
        # densify: walk each segment every ~0.33 m, both edges
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
    # plaza ring accents
    for i in range(40):
        a = math.tau * i / 40
        edge_spots.append((math.cos(a) * (5.8 + _r.uniform(0, 0.7)), math.sin(a) * (5.8 + _r.uniform(0, 0.7))))
    for (tx, ty) in edge_spots:
        if _r.random() < 0.86:
            h = 0.12 + _r.uniform(0, 0.12)
            ret = bmesh.ops.create_cone(bm_t, radius1=0.10 + _r.uniform(0, 0.05), radius2=0.014, depth=h, cap_ends=True, segments=5)
            bmesh.ops.translate(bm_t, vec=(tx, ty, h / 2), verts=ret['verts'])
        else:
            ret = bmesh.ops.create_uvsphere(bm_p, u_segments=5, v_segments=3, radius=0.05 + _r.uniform(0, 0.035))
            bmesh.ops.translate(bm_p, vec=(tx, ty, 0.03), verts=ret['verts'])
    tuft_mesh = bpy.data.meshes.new(prefix + "_tufts_mesh")
    bm_t.to_mesh(tuft_mesh)
    bm_t.free()
    set_vertex_color(tuft_mesh, PAL["tide_teal"])
    link_mesh(tuft_mesh, prefix + "_tufts", g, col)
    pebble_mesh = bpy.data.meshes.new(prefix + "_pebbles_mesh")
    bm_p.to_mesh(pebble_mesh)
    bm_p.free()
    set_vertex_color(pebble_mesh, PAL["basalt"])
    link_mesh(pebble_mesh, prefix + "_pebbles", g, col)


# ================================================================ props
def build_crate_stack(col, lod):
    p = f"lod{lod}__crate_stack"
    shell = make_mat("mat_crate_shell", FAM_SHELL, roughness=0.85)
    fiber = make_mat("mat_crate_fiber", FAM_FIBER, roughness=0.95)
    c1 = prim_box(p + "_crate_a", shell, col, (0.62, 0.62, 0.5), (-0.18, 0.1, 0.25), rot=(0, 0, 0.12), vcol=PAL["warm_apricot"])
    prim_box(p + "_crate_a_bat1", shell, col, (0.66, 0.08, 0.06), (-0.18, 0.1, 0.13), rot=(0, 0, 0.12), vcol=scale_color(PAL["warm_apricot"], 0.8))
    prim_box(p + "_crate_a_bat2", shell, col, (0.66, 0.08, 0.06), (-0.18, 0.1, 0.39), rot=(0, 0, 0.12), vcol=scale_color(PAL["warm_apricot"], 0.8))
    for (dz, dy) in [(0.21, 0.315), (0.31, 0.315)]:
        prim_box(p + f"_crate_a_slat{int(dz*100)}", shell, col, (0.635, 0.02, 0.05),
                 (-0.18 + math.sin(0.12) * (0.31 - dy) * 0, 0.1 + dy, dz), rot=(0, 0, 0.12),
                 vcol=scale_color(PAL["warm_apricot"], 0.68))
    c2 = prim_box(p + "_crate_b", shell, col, (0.5, 0.5, 0.42), (-0.12, -0.02, 0.5 + 0.21), rot=(0, 0, -0.22), vcol=PAL["bone_white"])
    prim_box(p + "_crate_b_bat1", shell, col, (0.54, 0.07, 0.05), (-0.12, -0.02, 0.5 + 0.1), rot=(0, 0, -0.22), vcol=scale_color(PAL["bone_white"], 0.78))
    prim_box(p + "_crate_b_bat2", shell, col, (0.54, 0.07, 0.05), (-0.12, -0.02, 0.5 + 0.33), rot=(0, 0, -0.22), vcol=scale_color(PAL["bone_white"], 0.78))
    if lod == 0:
        prim_box(p + "_crate_c", shell, col, (0.44, 0.44, 0.36), (0.38, -0.18, 0.18), rot=(0, 0, 0.4), vcol=scale_color(PAL["warm_apricot"], 0.9))
        prim_box(p + "_crate_c_bat", shell, col, (0.48, 0.07, 0.05), (0.38, -0.18, 0.09), rot=(0, 0, 0.4), vcol=scale_color(PAL["warm_apricot"], 0.72))
    s1 = prim_sphere(p + "_sack_a", fiber, col, 0.24, (0.55, 0.28, 0.15), seg=8, ring=6, scale=(1.15, 0.95, 0.72), vcol=PAL["dusk_indigo"])
    if lod == 0:
        prim_sphere(p + "_sack_b", fiber, col, 0.20, (0.78, 0.02, 0.12), seg=8, ring=6, scale=(1.1, 0.9, 0.7), vcol=scale_color(PAL["dusk_indigo"], 1.25))
    # contact hint
    prim_cylinder(p + "_contact", shell, col, 0.62, 0.62, 0.02, (0.05, 0.0, 0.01), seg=8, vcol=(0.35, 0.28, 0.22, 1.0))


def build_drying_rack(col, lod):
    p = f"lod{lod}__drying_rack"
    shell = make_mat("mat_rack_shell", FAM_SHELL_DARK, roughness=0.85)
    fiber = make_mat("mat_rack_fiber", FAM_FIBER, roughness=0.95)
    for sx in (-1, 1):
        prim_cylinder(p + f"_post_{sx}", shell, col, 0.045, 0.06, 1.85, (sx * 0.72, 0, 0.925), seg=8, vcol=FAM_SHELL_DARK)
    prim_cylinder(p + "_crossbar", shell, col, 0.035, 0.035, 1.55, (0, 0, 1.78), seg=8, rot=(0, math.pi / 2, 0), vcol=scale_color(FAM_SHELL_DARK, 1.3))
    strips = [(-0.42, PAL["hearth_amber"], 0.10), (-0.02, PAL["tide_teal"], -0.07), (0.38, PAL["coral_clay"], 0.13)]
    for i, (x, c, tilt) in enumerate(strips):
        s = prim_box(p + f"_strip_{i}", fiber, col, (0.30, 0.025, 0.52), (x, 0, 1.5), rot=(tilt, 0, 0), vcol=c)
        prim_cylinder(p + f"_knot_{i}", fiber, col, 0.018, 0.018, 0.09, (x, 0, 1.74), seg=6, vcol=scale_color(c, 0.6))
    # anchor pennant (NPC 驻点识别物)
    if lod == 0:
        prim_box(p + "_pennant", fiber, col, (0.22, 0.02, 0.3), (0.66, 0, 1.62), rot=(0.2, 0, 0.15), vcol=PAL["lichen_mint"])
    prim_cylinder(p + "_contact", shell, col, 0.6, 0.6, 0.02, (0, 0, 0.01), seg=8, vcol=(0.35, 0.28, 0.22, 1.0))


def build_amphora_cluster(col, lod):
    p = f"lod{lod}__amphora"
    ceramic = make_mat("mat_amphora", FAM_CERAMIC, roughness=0.9)
    prim_cylinder(p + "_tray", ceramic, col, 0.52, 0.6, 0.07, (0, 0, 0.035), seg=10, vcol=scale_color(FAM_CERAMIC, 0.9))
    profiles = [
        ([(0.16, 0.0), (0.19, 0.1), (0.21, 0.24), (0.17, 0.4), (0.10, 0.52), (0.07, 0.58)], (-0.18, 0.08)),
        ([(0.13, 0.0), (0.16, 0.08), (0.18, 0.2), (0.14, 0.34), (0.08, 0.44), (0.06, 0.48)], (0.22, -0.1)),
        ([(0.11, 0.0), (0.13, 0.07), (0.145, 0.16), (0.11, 0.27), (0.065, 0.34), (0.05, 0.38)], (0.02, 0.3)),
    ]
    for i, (prof, (ox, oy)) in enumerate(profiles):
        bm = bmesh.new()
        rings = []
        segs = 10
        for (rad, dz) in prof:
            ring = []
            for k in range(segs):
                a = math.tau * k / segs
                ring.append(bm.verts.new((rad * math.cos(a), rad * math.sin(a), dz)))
            rings.append(ring)
        for j in range(len(rings) - 1):
            for k in range(segs):
                k2 = (k + 1) % segs
                bm.faces.new([rings[j][k], rings[j][k2], rings[j + 1][k2], rings[j + 1][k]])
        bot = bm.verts.new((0, 0, prof[-1][1]))
        for k in range(segs):
            k2 = (k + 1) % segs
            bm.faces.new([bot, rings[-1][k], rings[-1][k2]])
        mesh = bpy.data.meshes.new(p + f"_v{i}_mesh")
        bm.to_mesh(mesh)
        bm.free()
        set_vertex_color(mesh, scale_color(FAM_CERAMIC, 1.0 - 0.06 * i))
        o = link_mesh(mesh, p + f"_v{i}", ceramic, col)
        o.location = (ox, oy, 0.07)
    prim_cylinder(p + "_contact", ceramic, col, 0.58, 0.58, 0.02, (0, 0, 0.01), seg=10, vcol=(0.35, 0.28, 0.22, 1.0))


def export_glb(name):
    out = os.path.join(EXPORT_DIR, name + ".glb")
    bpy.ops.object.select_all(action="DESELECT")
    col = bpy.data.collections[name]
    for obj in col.objects:
        obj.select_set(True)
    # export_vertex_color="ACTIVE": the default ("MATERIAL") emits a phantom white
    # COLOR_0 ahead of the authored layer, and Godot's COLOR builtin only reads
    # COLOR_0 — so every hand-authored per-part tint was silently dropped.
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True,
                              export_yup=True, export_apply=True,
                              export_vertex_color="ACTIVE")
    print(f"SETTLEMENT_EXPORT {name} ({os.path.getsize(out)/1024:.0f} KB)")


def main():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    reset_scene()
    builders = {
        "env_hut_residential_a": lambda col: [build_hut_a(col, lod) for lod in (0, 1, 2)],
        "env_hut_residential_b": lambda col: [build_hut_b(col, lod) for lod in (0, 1, 2)],
        "env_ground_market_a": build_ground_v2,
        "fol_ground_tufts_a": build_tufts,
        "prp_crate_stack_a": lambda col: [build_crate_stack(col, lod) for lod in (0, 1)],
        "prp_drying_rack_a": lambda col: [build_drying_rack(col, lod) for lod in (0, 1)],
        "prp_amphora_cluster_a": lambda col: [build_amphora_cluster(col, lod) for lod in (0, 1)],
    }
    for name, build in builders.items():
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
        build(col)
        export_glb(name)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print("ENV_SETTLEMENT_DONE blend=%s" % BLEND)


if __name__ == "__main__":
    main()
