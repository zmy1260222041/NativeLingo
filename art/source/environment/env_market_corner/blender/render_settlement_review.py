"""Render settlement review views from the exported env GLBs (Blender-side).

Replaces the Godot-window capture loop: the game window may stay in the
background the whole time — macOS stops compositing (and even SubViewport
UPDATE_ONCE) for fully occluded Godot windows, so visual iteration happens
here instead, mirroring main.gd placements + §3.2 白昼 lighting.

Run headless:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/environment/env_market_corner/blender/render_settlement_review.py -- --out <dir>

Game(x, y_up, z) -> Blender(x, y = -z_game, z = y_game); game yaw -> -Z rot.
"""
import bpy
import math
import mathutils
import os
import sys

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
GLB_DIR = os.path.join(HERE, "export")

# (file, blender_location, z_rotation_degrees)
LAYOUT = [
    ("env_ground_market_a.glb",      (0.0, 0.0, 0.0),   0.0),
    ("fol_ground_tufts_a.glb",       (0.0, 0.0, 0.0),   0.0),
    ("env_market_stall_a.glb",       (-1.8, 2.2, 0.0),  0.0),
    ("env_hut_residential_a.glb",    (-6.0, 5.0, 0.0),  180.0),
    ("env_hut_residential_b.glb",    (5.0, 7.0, 0.0),   180.0),
    ("env_hut_residential_a.glb",    (8.0, -3.0, 0.0),  0.0),
    ("env_hut_residential_b.glb",    (-7.0, -6.0, 0.0), 0.0),
    ("prp_crate_stack_a.glb",        (-3.9, 1.0, 0.0),  -34.0),
    ("prp_amphora_cluster_a.glb",    (1.6, 0.4, 0.0),   23.0),
    ("prp_food_token_c.glb",         (-2.45, 2.05, 1.12), 40.0),
    ("prp_food_token_b.glb",         (-1.15, 2.3, 1.12), -15.0),
    ("prp_drying_rack_a.glb",        (-3.8, 0.6, 0.0),  -14.0),
    ("prp_crate_stack_a.glb",        (2.6, 8.2, 0.0),   -126.0),
    ("prp_drying_rack_a.glb",        (-8.9, -2.1, 0.0), 52.0),
    ("prp_amphora_cluster_a.glb",    (9.2, -8.3, 0.0),  -75.0),
    ("prp_crate_stack_a.glb",        (10.9, -7.0, 0.0), 29.0),
    ("prp_crate_stack_a.glb",        (-4.2, 7.6, 0.0),   -63.0),
    ("prp_amphora_cluster_a.glb",    (3.4, 8.6, 0.0),    -46.0),
    ("prp_crate_stack_a.glb",        (6.4, -4.4, 0.0),   69.0),
    ("prp_amphora_cluster_a.glb",    (1.2, -3.4, 0.0),   -115.0),
    ("prp_drying_rack_a.glb",        (-5.6, -4.6, 0.0),  -52.0),
    ("prp_crate_stack_a.glb",        (2.0, 4.6, 0.0),    -20.0),
    ("prp_amphora_cluster_a.glb",    (-8.6, -6.8, 0.0),  11.0),
    ("prp_crate_stack_a.glb",        (9.6, -5.4, 0.0),   -149.0),
    ("prp_lantern_market_a.glb",     (-3.2, 2.2, 0.0),  0.0),
    ("prp_lantern_market_a.glb",     (3.2, 0.2, 0.0),   0.0),
    ("prp_lantern_market_a.glb",     (-4.5, -1.8, 0.0), 0.0),
    ("prp_lantern_market_a.glb",     (4.6, 1.0, 0.0),   0.0),
    ("prp_lantern_market_a.glb",     (-1.7, 7.5, 0.0),  0.0),
    ("env_shelter_distant_a.glb",    (-7.0, -8.5, 0.0), 0.0),
    ("env_rock_facet_b.glb",         (-11.4, 10.2, 0.0), -46.0),
    ("env_rock_facet_a.glb",         (13.6, 9.2, 0.0),   -120.0),
    ("env_rock_facet_b.glb",         (-10.4, -12.8, 0.0), -17.0),
    ("env_rock_facet_b.glb",         (14.6, -3.2, 0.0),  -109.0),
    ("env_rock_facet_a.glb",         (-14.8, -3.8, 0.0), -17.0),
    ("fol_tree_stranger_a.glb",      (2.2, -5.6, 0.0),   -23.0),
    ("fol_tree_stranger_a.glb",      (-10.5, 6.5, 0.0),  -69.0),
    ("fol_tree_stranger_a.glb",      (10.8, 3.6, 0.0),   52.0),
    ("fol_tree_stranger_a.glb",      (-3.4, -12.2, 0.0), -137.0),
    ("fol_tree_stranger_a.glb",      (12.6, -9.6, 0.0),  -40.0),
    ("fol_tree_stranger_a.glb",      (-5.5, 9.5, 0.0),   -97.0),
    ("env_ridge_distant_a.glb",      (0.0, 0.0, 0.0),    0.0),
]

# game review views (position, look_at, fov) -> blender coords
VIEWS = [
    ("market_core",     (1.6, -3.8, 2.5),  (-1.8, 2.0, 1.1),  58),
    ("market_wide",     (7.0, -10.0, 7.0), (0.0, 2.0, 1.0),   55),
    ("hut_row",         (2.5, -1.5, 2.0),  (-6.0, 5.0, 1.6),  55),
    ("hut_close",       (-3.0, 0.6, 1.9),  (-6.0, 5.0, 1.5),  55),
    ("ground_close",    (-1.2, -0.8, 0.7), (-2.2, 2.6, 0.35), 65),
    ("stall_close",     (0.6, 0.4, 1.8),   (-1.8, 2.2, 1.3),  55),
    ("settlement_wide", (14.0, -14.0, 9.0), (-2.0, 3.0, 0.5), 50),
    ("hero_tree",       (5.6, -8.2, 3.0),  (2.2, -5.6, 2.4),  50),
]

PLAZA_COLOR = (0xC7/255, 0x7A/255, 0x5E/255, 1.0)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def wire_vertex_colors(obj):
    """Multiply every material's base color by the mesh's Color attribute so
    the authored per-part tints (family ladder, wear gradient, contact black)
    show up in the Principled/EEVEE preview exactly as Godot's cel shader
    composes them."""
    if obj.type != 'MESH' or obj.data.color_attributes.get("Color") is None:
        return
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        if any(n.type == 'VERTEX_COLOR' for n in mat.node_tree.nodes):
            continue
        tree = mat.node_tree
        bsdf = tree.nodes.get("Principled BSDF")
        if bsdf is None:
            continue
        vc = tree.nodes.new('ShaderNodeVertexColors')
        vc.layer_name = "Color"
        mix = tree.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs[6].default_value = bsdf.inputs["Base Color"].default_value  # A
        mix.inputs[7].default_value = (1.0, 1.0, 1.0, 1.0)  # B
        tree.links.new(vc.outputs["Color"], mix.inputs[6])
        tree.links.new(mix.outputs["Result Color"], bsdf.inputs["Base Color"])


def add_base_plane():
    """80m 基座（镜像 main.gd Ground 80×80）：让远脊落地、宽镜不露空。"""
    mat = bpy.data.materials.new("base_mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.847, 0.78, 0.60, 1.0)  # palette.sand
    bsdf.inputs["Roughness"].default_value = 0.95
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=40.0)
    mesh = bpy.data.meshes.new("base_mesh")
    bm.to_mesh(mesh)
    bm.free()
    base = bpy.data.objects.new("BasePlane", mesh)
    bpy.context.collection.objects.link(base)
    base.location = (0, 0, -0.02)
    base.data.materials.append(mat)


def add_plaza():
    mat = bpy.data.materials.new("plaza_mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = PLAZA_COLOR
    bsdf.inputs["Roughness"].default_value = 0.95
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, radius1=5.32, radius2=5.32, depth=0.08, cap_ends=True, segments=48)
    mesh = bpy.data.meshes.new("plaza_mesh")
    bm.to_mesh(mesh)
    bm.free()
    plaza = bpy.data.objects.new("MeetingPlaza", mesh)
    bpy.context.collection.objects.link(plaza)
    plaza.location = (0, 0, 0.055)
    plaza.name = "MeetingPlaza"
    plaza.data.materials.append(mat)


def add_glowplants_ring():
    bpy.ops.import_scene.gltf(filepath=os.path.join(GLB_DIR, "fol_glowplant_a.glb"))
    src = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    for i in range(16):
        a = math.tau * i / 16.0
        r = 11.5 + (i * 0.73) % 3.2
        for o in src:
            dup = o.copy()
            dup.data = o.data
            bpy.context.collection.objects.link(dup)
            dup.location = mathutils.Vector((math.cos(a) * r, math.sin(a) * r, 0.0))
            dup.rotation_euler.z = a + math.pi
            wire_vertex_colors(dup)
    for o in src:
        bpy.data.objects.remove(o, do_unlink=True)


def main():
    argv = sys.argv
    out_dir = "/tmp/env_review/blender"
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    os.makedirs(out_dir, exist_ok=True)
    reset_scene()

    for file, loc, rot_z in LAYOUT:
        bpy.ops.import_scene.gltf(filepath=os.path.join(GLB_DIR, file))
        roots = [o for o in bpy.context.selected_objects if o.parent is None]
        for obj in bpy.context.selected_objects:
            wire_vertex_colors(obj)
        # runtime env_lod only ever shows lod0__ in review lenses — hide the
        # merged/silhouette LOD meshes so assets don't render triple-nested
        for obj in bpy.context.selected_objects:
            if obj.type == 'MESH' and obj.name.startswith(("lod1__", "lod2__")):
                obj.hide_render = True
                obj.hide_viewport = True
        for root in roots:
            root.location = mathutils.Vector(loc)
            root.rotation_euler.z += math.radians(rot_z)

    add_base_plane()
    add_plaza()
    add_glowplants_ring()

    # §3.2 白昼 lighting (mirrors main.gd day_time≈120)
    bpy.ops.object.light_add(type='SUN')
    sun = bpy.context.active_object
    sun.name = "Sun"
    sun.rotation_euler = (math.radians(55), 0, math.radians(28))
    sun.data.energy = 3.6
    sun.data.color = (1.0, 0.94, 0.81)
    sun.data.angle = math.radians(2.0)
    bpy.ops.object.light_add(type='SUN')
    fill = bpy.context.active_object
    fill.name = "SkyFill"
    fill.rotation_euler = (math.radians(-40), 0, math.radians(200))
    fill.data.energy = 0.55
    fill.data.color = (0.56, 0.67, 0.71)
    world = bpy.data.worlds.new("ReviewWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.88, 0.80, 0.70, 1.0)
    bg.inputs["Strength"].default_value = 0.9

    bpy.ops.object.camera_add()
    cam = bpy.context.active_object
    cam.name = "ReviewCam"
    bpy.context.scene.camera = cam

    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    scene.render.image_settings.file_format = 'PNG'
    scene.eevee.taa_render_samples = 32
    scene.view_settings.view_transform = 'Standard'

    for name, pos, look, fov in VIEWS:
        cam.location = mathutils.Vector(pos)
        direction = mathutils.Vector(look) - cam.location
        cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        cam.data.lens = 0.5 * 36.0 / math.tan(math.radians(fov / 2.0))  # 36 mm sensor width
        out_path = os.path.join(out_dir, name + ".png")
        scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print("SETTLEMENT_REVIEW_RENDER", out_path)

    print("SETTLEMENT_REVIEW_DONE", out_dir)


if __name__ == "__main__":
    main()
