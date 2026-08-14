"""Preview renders of hut v02 — hide lod1/2, wire vertex colors, EEVEE."""
import math
import os

import bpy
import mathutils

REPO = "/Users/a86138/Developer/NativeLingo"
GLB_DIR = os.path.join(REPO, "art/source/environment/env_market_corner/export")
OUT_DIR = os.path.join(REPO, "art/source/environment/env_market_corner/validation")

SHOTS = [
    ("env_hut_residential_a.glb", "hut_a_threeq", 7.4, 1.7, 38),
    ("env_hut_residential_a.glb", "hut_a_front", 8.4, 1.7, 0),
    ("env_hut_residential_a.glb", "hut_a_door", 4.6, 1.35, 8),
    ("env_hut_residential_b.glb", "hut_b_threeq", 7.0, 1.8, 40),
    ("env_hut_residential_b.glb", "hut_b_front", 6.4, 1.6, 0),
    ("env_shelter_distant_a.glb", "shelter_threeq", 8.0, 1.8, 38),
    ("env_hut_residential_c.glb", "hut_c_threeq", 7.6, 2.0, 36),
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
        if obj.type == "MESH" and not obj.name.startswith("lod0__"):
            obj.hide_render = True
            obj.hide_viewport = True
        elif obj.type == "MESH":
            wire_vertex_colors(obj)


def render_shot(glb, name, dist, target_h, yaw_deg):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(GLB_DIR, glb))
    hide_non_lod0()
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
    cam_loc = (dist * math.sin(yaw), -dist * math.cos(yaw), target_h + dist * 0.18)
    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.active_object
    cam.data.lens = 45
    focus = mathutils.Vector((0.0, 0.0, target_h))
    cam.rotation_euler = (focus - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene = bpy.context.scene
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    scene.render.filepath = os.path.join(OUT_DIR, name + ".png")
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    print("HUT_PREVIEW", scene.render.filepath)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for shot in SHOTS:
        render_shot(*shot)


if __name__ == "__main__":
    main()
