"""Phase 3 kit: terrace, plaza, heater, reservoir, beacon.

Z-up, origin at base, same family ladder as huts_v02.
Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \\
    --python art/source/environment/env_market_corner/blender/model_env_phase3.py
"""
from __future__ import annotations

import math
import os

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
BLEND = os.path.join(HERE, "blender/env_phase3.blend")
EXPORT_DIR = os.path.join(HERE, "export")
TEX_DIR = os.path.join(HERE, "textures")

FAM_CERAMIC = (0xE7 / 255, 0xD2 / 255, 0xA3 / 255, 1.0)
FAM_SHELL = (0xD8 / 255, 0x66 / 255, 0x5B / 255, 1.0)
FAM_SHELL_DARK = (0x5A / 255, 0x3F / 255, 0x58 / 255, 1.0)
FAM_ALLOY = (0x4B / 255, 0x52 / 255, 0x68 / 255, 1.0)
FAM_TEAL = (0x2F / 255, 0x8C / 255, 0x87 / 255, 1.0)
FAM_AMBER = (0xF2 / 255, 0xA8 / 255, 0x5B / 255, 1.0)
PACKED = (0xB5 / 255, 0x96 / 255, 0x6E / 255, 1.0)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mat(name, color, roughness=0.85):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def hook_image(mat, path):
    if not os.path.isfile(path) or mat is None:
        return
    img = bpy.data.images.load(path, check_existing=True)
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])


def new_fam():
    return {"bm": bmesh.new(), "col": {}}


def paint(fam, verts, color):
    for vert in verts:
        fam["col"][vert] = color


def _xform(bm, verts, loc, euler=(0, 0, 0)):
    mat = Matrix.Translation(Vector(loc)) @ Euler(euler, "XYZ").to_matrix().to_4x4()
    bmesh.ops.transform(bm, verts=verts, matrix=mat)


def add_box(fam, size, loc, euler=(0, 0, 0), color=FAM_SHELL):
    bm = fam["bm"]
    ret = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=ret["verts"])
    _xform(bm, ret["verts"], loc, euler)
    paint(fam, ret["verts"], color)
    return ret["verts"]


def add_cyl(fam, r1, r2, depth, loc, segs=8, euler=(0, 0, 0), color=FAM_SHELL):
    bm = fam["bm"]
    ret = bmesh.ops.create_cone(bm, radius1=r1, radius2=r2, depth=depth, cap_ends=True, segments=segs)
    _xform(bm, ret["verts"], loc, euler)
    paint(fam, ret["verts"], color)
    return ret["verts"]


def finish(fam, name, fallback, mat, col):
    bm = fam["bm"]
    if len(bm.verts) == 0:
        bm.free()
        return
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table()
    colors = [fam["col"].get(v, fallback) for v in bm.verts]
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    attr = mesh.color_attributes.new(name="Color", domain="CORNER", type="FLOAT_COLOR")
    for loop in mesh.loops:
        attr.data[loop.index].color = colors[loop.vertex_index]
    if mesh.uv_layers.get("UVMap") is None:
        mesh.uv_layers.new(name="UVMap")
    uv = mesh.uv_layers["UVMap"]
    for poly in mesh.polygons:
        n = poly.normal
        for li, vi in zip(poly.loop_indices, poly.vertices):
            co = mesh.vertices[vi].co
            if abs(n.z) >= abs(n.x) and abs(n.z) >= abs(n.y):
                uv.data[li].uv = (co.x * 0.4, co.y * 0.4)
            elif abs(n.y) >= abs(n.x):
                uv.data[li].uv = (co.x * 0.4, co.z * 0.4)
            else:
                uv.data[li].uv = (co.y * 0.4, co.z * 0.4)
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    obj.data.materials.append(mat)


def build_terrace(col, mats):
    shell, clay = new_fam(), new_fam()
    h = 0.52
    add_box(clay, (2.9, 2.05, h), (0, 0, h / 2), color=FAM_CERAMIC)
    add_box(shell, (3.05, 0.14, h + 0.08), (0, 1.02, h / 2 + 0.02), color=FAM_SHELL_DARK)
    add_box(shell, (0.14, 2.05, h + 0.08), (-1.48, 0, h / 2 + 0.02), color=FAM_SHELL_DARK)
    add_box(shell, (0.14, 2.05, h + 0.08), (1.48, 0, h / 2 + 0.02), color=FAM_SHELL_DARK)
    for i, (zh, yd, xs) in enumerate(((0.16, -1.28, 2.4), (0.32, -1.52, 2.15), (0.48, -1.74, 1.9))):
        add_box(clay, (xs, 0.36, 0.10), (0, yd, zh), color=(0.86, 0.74, 0.55, 1.0))
    add_box(shell, (0.55, 0.08, 0.22), (1.05, -0.2, h + 0.08), color=FAM_ALLOY)
    finish(shell, "lod0__terrace_shell", FAM_SHELL_DARK, mats["shell"], col)
    finish(clay, "lod0__terrace_clay", FAM_CERAMIC, mats["clay"], col)


def build_plaza(col, mats):
    clay, packed = new_fam(), new_fam()
    add_cyl(clay, 5.35, 5.55, 0.10, (0, 0, 0.04), segs=10, color=FAM_CERAMIC)
    add_cyl(packed, 4.55, 4.7, 0.06, (0, 0, 0.09), segs=10, color=PACKED)
    add_cyl(clay, 5.6, 5.6, 0.04, (0, 0, 0.015), segs=10, color=(0.16, 0.14, 0.13, 1.0))
    finish(clay, "lod0__plaza_clay", FAM_CERAMIC, mats["clay"], col)
    finish(packed, "lod0__plaza_packed", PACKED, mats["ground"], col)


def build_heater(col, mats):
    alloy, clay = new_fam(), new_fam()
    add_cyl(clay, 0.52, 0.62, 0.18, (0, 0, 0.09), segs=8, color=FAM_CERAMIC)
    add_cyl(alloy, 0.36, 0.40, 1.05, (0, 0, 0.72), segs=8, color=FAM_ALLOY)
    add_box(alloy, (0.18, 0.06, 0.42), (0.38, 0, 0.78), color=(0.28, 0.30, 0.38, 1.0))
    add_cyl(clay, 0.22, 0.28, 0.12, (0, 0, 1.28), segs=8, color=FAM_AMBER)
    add_box(alloy, (0.08, 0.08, 0.22), (0.18, 0.18, 0.55), color=FAM_SHELL_DARK)
    add_cyl(alloy, 0.42, 0.42, 0.05, (0, 0, 0.42), segs=8, color=(0.62, 0.65, 0.74, 1.0))
    add_cyl(alloy, 0.42, 0.42, 0.05, (0, 0, 1.05), segs=8, color=(0.62, 0.65, 0.74, 1.0))
    finish(alloy, "lod0__heater_alloy", FAM_ALLOY, mats["alloy"], col)
    finish(clay, "lod0__heater_clay", FAM_CERAMIC, mats["clay"], col)


def build_reservoir(col, mats):
    clay, alloy = new_fam(), new_fam()
    add_cyl(clay, 0.62, 0.72, 0.22, (0, 0, 0.11), segs=10, color=FAM_CERAMIC)
    add_cyl(clay, 0.50, 0.58, 0.48, (0, 0, 0.46), segs=10, color=(0.82, 0.72, 0.54, 1.0))
    add_cyl(alloy, 0.60, 0.60, 0.06, (0, 0, 0.70), segs=10, color=FAM_ALLOY)
    add_cyl(clay, 0.46, 0.46, 0.04, (0, 0, 0.62), segs=10, color=FAM_TEAL)
    add_box(alloy, (0.08, 0.08, 0.55), (0.58, 0, 0.38), color=FAM_ALLOY)
    add_box(alloy, (0.08, 0.08, 0.55), (-0.58, 0, 0.38), color=FAM_ALLOY)
    finish(clay, "lod0__reservoir_clay", FAM_CERAMIC, mats["clay"], col)
    finish(alloy, "lod0__reservoir_alloy", FAM_ALLOY, mats["alloy"], col)


def build_beacon(col, mats):
    alloy, clay = new_fam(), new_fam()
    add_cyl(clay, 0.48, 0.62, 0.28, (0, 0, 0.14), segs=8, color=FAM_CERAMIC)
    add_cyl(alloy, 0.16, 0.20, 1.15, (0, 0, 0.86), segs=6, color=FAM_ALLOY)
    add_box(clay, (0.22, 0.22, 0.55), (0, 0, 1.55), euler=(0.18, 0.1, 0.4), color=FAM_TEAL)
    finish(alloy, "lod0__beacon_alloy", FAM_ALLOY, mats["alloy"], col)
    finish(clay, "lod0__beacon_clay", FAM_CERAMIC, mats["clay"], col)


def export_glb(name):
    out = os.path.join(EXPORT_DIR, name + ".glb")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.data.collections[name].objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=out, export_format="GLB", use_selection=True,
        export_yup=True, export_apply=True, export_vertex_color="ACTIVE",
    )
    print("PHASE3_EXPORT", name, f"{os.path.getsize(out)/1024:.0f}KB")


def main():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    reset_scene()
    mats = {
        "shell": make_mat("mat_p3_shell", FAM_SHELL, 0.85),
        "clay": make_mat("mat_p3_clay", FAM_CERAMIC, 0.9),
        "alloy": make_mat("mat_p3_alloy", FAM_ALLOY, 0.55),
        "ground": make_mat("mat_p3_ground", PACKED, 0.95),
    }
    hook_image(mats["shell"], os.path.join(TEX_DIR, "tex_shell_tile_1k.png"))
    hook_image(mats["clay"], os.path.join(TEX_DIR, "tex_clay_tile_1k.png"))
    hook_image(mats["ground"], os.path.join(TEX_DIR, "tex_ground_packed_1k.png"))
    jobs = {
        "env_terrace_market_a": build_terrace,
        "env_plaza_market_a": build_plaza,
        "prp_heater_old": build_heater,
        "prp_reservoir_a": build_reservoir,
        "prp_beacon_market_a": build_beacon,
    }
    for name, build in jobs.items():
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
        build(col, mats)
        export_glb(name)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print("PHASE3_DONE")


if __name__ == "__main__":
    main()
