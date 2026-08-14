"""Hand-model the Phase 4 environment props for the 「白昼市场角落」 art-test.

One script, seven assets (art-bible §8.6 prefixes; §8.2 budget rows):
  - prp_lantern_market_a   medium prop, LOD0/1, emissive bulb
  - fol_glowplant_a        vegetation single plant (MultiMesh at runtime §8.5)
  - env_rock_market_a/b    rock variants, shared atlas intent, silhouette LOD
  - env_ground_market_a    ground + path decals + drain grate, vertex-color zones
  - env_shelter_distant_a  distant nav-point silhouette, vertex color only
  - prp_food_token_a/b/c   three small pickup shapes

Same discipline as model_stall_a.py: Blender Z-up authored, front faces +Y so
the glTF Z-up->Y-up conversion lands -Z forward in Godot; origin at the base
(lowest point z=0); geometry authored at world coords (no apply-scale gotcha).

Run headless:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/environment/env_market_corner/blender/model_env_props.py
"""
import bpy
import math
import os

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
BLEND = os.path.join(HERE, "blender/env_props.blend")
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


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mat(name, color, emission=None, roughness=0.8):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = emission
        bsdf.inputs["Emission Strength"].default_value = 5.0
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


def prim_cylinder(name, mat, collection, r1, r2, depth, loc, seg=12):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, radius1=r1, radius2=r2, depth=depth, cap_ends=True, segments=seg)
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    o = link_mesh(mesh, name, mat, collection)
    o.location = loc
    return o


def prim_sphere(name, mat, collection, radius, loc, seg=16, ring=10):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=radius)
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    o = link_mesh(mesh, name, mat, collection)
    o.location = loc
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.shade_smooth()
    return o


def prim_box(name, mat, collection, size, loc, rot=(0, 0, 0)):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    o = link_mesh(mesh, name, mat, collection)
    o.rotation_euler = rot
    return o


# ---------------------------------------------------------------- lantern
def build_lantern(col, lod, stem, bulb):
    prefix = f"lod{lod}__lantern"
    seg = 12 if lod == 0 else 8
    prim_cylinder(prefix + "_stem", stem, col, 0.055, 0.08, 1.7, (0, 0, 0.85), seg=seg)
    prim_cylinder(prefix + "_hanger", stem, col, 0.03, 0.03, 0.3, (0, 0, 1.95), seg=seg)
    prim_cylinder(prefix + "_hook", stem, col, 0.02, 0.02, 0.12, (0, 0, 2.13), seg=seg)
    b = prim_sphere(prefix + "_bulb", bulb, col, 0.23, (0, 0, 1.68), seg=seg, ring=8 if lod == 1 else 10)
    set_vertex_color(b.data, PAL["hearth_amber"])


# ---------------------------------------------------------------- glowplant
def build_glowplant(col):
    prefix = "fol_glowplant_a"
    stem = make_mat("mat_fol_glowplant", PAL["tide_teal"], roughness=0.8)
    # slightly curved stem (two stacked tapering cylinders); bulb tinted mint by
    # vertex color on the same single material (§8.2 vegetation ≤1 slot)
    prim_cylinder(prefix + "_stem_lo", stem, col, 0.07, 0.05, 0.7, (0, 0, 0.35), seg=8)
    prim_cylinder(prefix + "_stem_hi", stem, col, 0.05, 0.03, 0.6, (0.02, 0.03, 1.0), seg=8)
    b = prim_sphere(prefix + "_bulb", stem, col, 0.25, (0.04, 0.06, 1.32), seg=10, ring=7)
    set_vertex_color(b.data, PAL["lichen_mint"])


# ---------------------------------------------------------------- rocks
def build_rock(col, variant, lod, m):
    prefix = f"lod{lod}__rock_{variant}"
    import bmesh
    import random as _r
    bm = bmesh.new()
    # LOD0 finer (subdiv 2), LOD1 coarse (subdiv 1) — silhouette preserved
    bmesh.ops.create_icosphere(bm, subdivisions=2 - lod, radius=1.0)
    _r.seed(7 if variant == "a" else 23)
    for v in bm.verts:
        v.co.x += _r.uniform(-0.18, 0.18)
        v.co.y += _r.uniform(-0.18, 0.18)
        v.co.z += _r.uniform(-0.14, 0.14)
    # squash toward a low rock form
    for v in bm.verts:
        v.co.z *= 0.55
    mesh = bpy.data.meshes.new(prefix + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    o = link_mesh(mesh, prefix, m, col)
    if variant == "a":
        o.scale = (1.9, 1.6, 1.0)
    else:
        o.scale = (1.5, 1.4, 0.9)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.shade_smooth()
    # lift so the lowest vertex (after randomize + squash) sits exactly at z=0
    z_min = min((v.co * o.scale).z for v in mesh.vertices)
    o.location.z = -z_min


# ---------------------------------------------------------------- ground
def build_ground(col):
    prefix = "env_ground_market_a"
    g = make_mat("mat_env_ground", PAL["dust_cream"], roughness=0.95)
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(28.0, 28.0, 0.5), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, -0.25), verts=bm.verts)
    mesh = bpy.data.meshes.new(prefix + "_ground_mesh")
    bm.to_mesh(mesh)
    bm.free()
    o = link_mesh(mesh, prefix + "_ground", g, col)
    # vertex color macro zones: dust-cream sand dominates; dusk-indigo at edges
    set_vertex_color(mesh, PAL["dust_cream"])
    # path decals (bone-white path toward the stall) + a drain grate — same
    # single ground material, semantic colors via vertex color (§8.2 ground ≤1 slot)
    for (y, w) in [(2.0, 3.0), (3.6, 3.4), (5.2, 3.8)]:
        o = prim_box(prefix + f"_path_{y}", g, col, (w, 1.6, 0.02), (0, y, 0.01))
        set_vertex_color(o.data, PAL["bone_white"])
    o = prim_box(prefix + "_grate", g, col, (1.2, 0.8, 0.04), (3.0, -4.0, 0.02))
    set_vertex_color(o.data, PAL["silt_ink"])


# ---------------------------------------------------------------- shelter
def build_shelter(col):
    prefix = "env_shelter_distant_a"
    body = make_mat("mat_env_shelter_body", PAL["dusk_indigo"], roughness=0.9)
    prim_box(prefix + "_body", body, col, (4.5, 3.6, 2.8), (0, 0, 1.4))
    # roof prism
    import bmesh
    hw, d, h = 2.4, 3.6, 2.6
    bm = bmesh.new()
    verts = [(-hw, -d/2, 0), (hw, -d/2, 0), (0, -d/2, h),
             (-hw, d/2, 0), (hw, d/2, 0), (0, d/2, h)]
    faces = [(0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (0, 2, 5, 3)]
    for v in verts:
        bm.verts.new(v)
    bm.verts.ensure_lookup_table()
    for f in faces:
        bm.faces.new([bm.verts[i] for i in f])
    mesh = bpy.data.meshes.new(prefix + "_roof_mesh")
    bm.to_mesh(mesh)
    bm.free()
    set_vertex_color(mesh, PAL["bark_plum"])
    o = link_mesh(mesh, prefix + "_roof", body, col)
    o.location = (0, 0, 3.4)
    w = prim_box(prefix + "_window", body, col, (0.9, 0.1, 0.9), (1.3, 1.85, 1.7))
    set_vertex_color(w.data, PAL["hearth_amber"])


# ---------------------------------------------------------------- food tokens
def build_token(col, variant):
    prefix = f"prp_food_token_{variant}"
    m = make_mat(f"mat_prp_food_token_{variant}", PAL["lichen_mint"], roughness=0.5)
    import bmesh
    if variant == "a":
        # 种荚/水滴: ellipsoid with a small tip
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.16)
        for v in bm.verts:
            v.co.y *= 1.25
        mesh = bpy.data.meshes.new(prefix + "_mesh")
        bm.to_mesh(mesh)
        bm.free()
        o = link_mesh(mesh, prefix, m, col)
        o.location = (0, 0, 0.16)
    elif variant == "b":
        # berry cluster: three small spheres
        for i, (dx, dz, r) in enumerate([(-0.07, 0.10, 0.09), (0.07, 0.10, 0.09), (0.0, 0.22, 0.07)]):
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=r)
            mesh = bpy.data.meshes.new(f"{prefix}_{i}_mesh")
            bm.to_mesh(mesh)
            bm.free()
            o = link_mesh(mesh, f"{prefix}_{i}", m, col)
            o.location = (dx, 0, dz)
    else:
        # 陶碗装食物: shallow bowl + heap — one material, bowl tinted by vertex color
        bm = bmesh.new()
        rings = []
        prof = [(0.22, 0.0), (0.20, 0.02), (0.13, 0.06), (0.08, 0.08)]
        for j, (rad, dz) in enumerate(prof):
            ring = []
            for k in range(10):
                a = math.tau * k / 10
                ring.append(bm.verts.new((rad * math.cos(a), rad * math.sin(a), dz)))
            rings.append(ring)
        for j in range(len(rings) - 1):
            for k in range(10):
                k2 = (k + 1) % 10
                bm.faces.new([rings[j][k], rings[j][k2], rings[j+1][k2], rings[j+1][k]])
        ring_bot = rings[-1]
        bot = bm.verts.new((0, 0, prof[-1][1]))
        for k in range(10):
            k2 = (k + 1) % 10
            bm.faces.new([bot, ring_bot[k], ring_bot[k2]])
        mesh = bpy.data.meshes.new(prefix + "_bowl_mesh")
        bm.to_mesh(mesh)
        bm.free()
        set_vertex_color(mesh, PAL["coral_clay"])
        o = link_mesh(mesh, prefix + "_bowl", m, col)
        o.location = (0, 0, 0.0)
        heap = prim_sphere(prefix + "_heap", m, col, 0.10, (0, 0, 0.09), seg=10, ring=6)
        heap.scale = (1.1, 1.1, 0.8)


def export_glb(name):
    out = os.path.join(EXPORT_DIR, name + ".glb")
    # export ONLY this asset's collection — env_props.blend holds 9 collections,
    # and use_selection=False would bake every prior collection into each GLB
    bpy.ops.object.select_all(action="DESELECT")
    col = bpy.data.collections[name]
    for obj in col.objects:
        obj.select_set(True)
    # export_vertex_color="ACTIVE": see model_env_settlement.export_glb — the
    # default "MATERIAL" prepends a white COLOR_0 that masks the authored layer.
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True,
                              export_yup=True, export_apply=True,
                              export_vertex_color="ACTIVE")
    print(f"PROP_EXPORT {name} ({os.path.getsize(out)/1024:.0f} KB)")


def main():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    reset_scene()
    # env_ground_market_a is NOT built here: model_env_settlement.build_ground_v2
    # owns the ground (§5.4 three-layer wear network). The legacy build_ground
    # below is v1 and would overwrite that richer export with a flat slab.
    for name in ["prp_lantern_market_a", "fol_glowplant_a", "env_rock_market_a",
                 "env_rock_market_b", "env_shelter_distant_a",
                 "prp_food_token_a", "prp_food_token_b", "prp_food_token_c"]:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
        if name == "prp_lantern_market_a":
            stem = make_mat("mat_prp_lantern_alloy", PAL["silt_ink"], roughness=0.7)
            bulb = make_mat("mat_prp_lantern_bulb", PAL["bone_white"], emission=PAL["hearth_amber"], roughness=0.4)
            build_lantern(col, 0, stem, bulb)
            build_lantern(col, 1, stem, bulb)
        elif name == "fol_glowplant_a":
            build_glowplant(col)
        elif name.startswith("env_rock_market_"):
            rm = make_mat("mat_env_rock", PAL["basalt"], roughness=0.95)
            build_rock(col, name[-1], 0, rm)
            build_rock(col, name[-1], 1, rm)
        elif name == "env_shelter_distant_a":
            build_shelter(col)
        else:
            build_token(col, name[-1])
        export_glb(name)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print("ENV_PROPS_DONE blend=%s" % BLEND)


if __name__ == "__main__":
    main()
