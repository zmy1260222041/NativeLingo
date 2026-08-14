"""Preview lod0 tree + distant ridge after the connection/scale repair."""
import math
import os

import bpy
import mathutils

REPO = "/Users/a86138/Developer/NativeLingo"
GLB_DIR = os.path.join(REPO, "art/source/environment/env_market_corner/export")
OUT_DIR = os.path.join(REPO, "art/source/environment/env_market_corner/validation")

SHOTS = [
    ("fol_tree_stranger_a.glb", "tree_a_threeq", 7.2, 2.2, 38, True, 45),
    ("fol_tree_stranger_a.glb", "tree_a_branch", 4.4, 2.0, 12, True, 45),
    ("env_ridge_distant_a.glb", "ridge_skyline", 0.0, 4.2, 90, False, 28),
    ("env_ridge_distant_a.glb", "ridge_gap", 10.0, 2.2, 90, False, 32),
    ("env_ridge_distant_a.glb", "ridge_bowl", 0.0, 78.0, 0, False, 28),
    ("env_ridge_distant_a.glb", "ridge_valley", 0.0, 7.0, 0, False, 28),
]


def wire_vertex_colors(obj):
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        nt = mat.node_tree
        if any(n.type == "VERTEX_COLOR" for n in nt.nodes):
            continue
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        vcol = nt.nodes.new("ShaderNodeVertexColor")
        vcol.layer_name = "Color"
        nt.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])


def hide_non_lod0():
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        if not obj.name.startswith("lod0__"):
            obj.hide_render = True
            obj.hide_viewport = True
        else:
            wire_vertex_colors(obj)


def wire_all():
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            wire_vertex_colors(obj)


def render_shot(glb, name, dist, target_h, yaw_deg, lod0_only, lens):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(GLB_DIR, glb))
    if lod0_only:
        hide_non_lod0()
    else:
        wire_all()
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 0))
    sun = bpy.context.active_object
    sun.rotation_euler = (math.radians(52), math.radians(18), math.radians(28))
    sun.data.energy = 3.6
    sun.data.color = (1.0, 0.94, 0.84)
    world = bpy.data.worlds.new("W")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.86, 0.82, 0.74, 1.0)
    bg.inputs["Strength"].default_value = 0.85
    yaw = math.radians(yaw_deg)
    if name.endswith("_bowl"):
        cam_loc = (0.2, -0.2, target_h)
        focus = mathutils.Vector((0.0, 0.0, 0.0))
    elif name.endswith("_valley"):
        cam_loc = (0.0, -30.0, target_h)
        focus = mathutils.Vector((0.0, 8.0, 6.0))
    elif name.endswith("_skyline"):
        cam_loc = (0.0, 2.0, target_h)
        focus = mathutils.Vector((24.0, 0.0, 14.0))
    elif name.endswith("_gap"):
        cam_loc = (8.0, 1.0, target_h)
        focus = mathutils.Vector((22.0, 0.0, 2.5))
    else:
        cam_loc = (dist * math.sin(yaw), -dist * math.cos(yaw), target_h + dist * 0.18)
        focus = mathutils.Vector((0.0, 0.0, target_h))
    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.active_object
    cam.data.lens = lens
    cam.rotation_euler = (focus - mathutils.Vector(cam_loc)).to_track_quat("-Z", "Y").to_euler()
    scene = bpy.context.scene
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    os.makedirs(OUT_DIR, exist_ok=True)
    scene.render.filepath = os.path.join(OUT_DIR, name + ".png")
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    print("TREE_RIDGE_PREVIEW", scene.render.filepath)


def main():
    for shot in SHOTS:
        render_shot(*shot)


if __name__ == "__main__":
    main()
