"""Render validation stills of the v03 hut GLBs (same framing as v02 review)."""
import os
import bpy

REPO = "/Users/a86138/Developer/NativeLingo"
EXPORT = os.path.join(REPO, "art/source/environment/env_market_corner/export")
OUT = os.path.join(REPO, "art/source/environment/env_market_corner/validation")

bpy.ops.wm.read_factory_settings(use_empty=True)
for name in ("env_hut_residential_a", "env_hut_residential_b", "env_hut_residential_c", "env_shelter_distant_a"):
    bpy.ops.import_scene.gltf(filepath=os.path.join(EXPORT, name + ".glb"))

world = bpy.data.worlds.new("World")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.72, 0.78, 0.9, 1.0)
bg.inputs[1].default_value = 1.4
bpy.context.scene.world = world

key = bpy.data.lights.new("Key", "SUN")
key.energy = 3.0
key.angle = 0.9
key_obj = bpy.data.objects.new("Key", key)
key_obj.rotation_euler = (0.9, 0.2, 0.7)
bpy.context.collection.objects.link(key_obj)

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 42
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam

bpy.context.scene.render.resolution_x = 960
bpy.context.scene.render.resolution_y = 720
bpy.context.scene.render.engine = "BLENDER_EEVEE"
bpy.context.scene.render.image_settings.file_format = "PNG"

root = None  # objects are located by kit stem in the loop below

def frame(tag, cam_pos, look):
    cam.location = cam_pos
    direction = look - cam_pos
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.render.filepath = os.path.join(OUT, f"{tag}.png")
    bpy.ops.render.render(write_still=True)
    print("V03_SHOT", tag)

import mathutils
V = mathutils.Vector
for name, dist in (("env_hut_residential_a", 7.0), ("env_hut_residential_b", 7.5), ("env_hut_residential_c", 7.0), ("env_shelter_distant_a", 7.5)):
    objs = [o for o in bpy.data.objects if name in o.name or (o.type == "EMPTY" and name in o.name)]
    target = None
    for o in objs:
        if o.type in ("MESH", "EMPTY"):
            target = o
            break
    if target is None:
        # fall back: any object whose name contains the kit stem
        target = next((o for o in bpy.data.objects if "hut" in o.name.lower() or "shelter" in o.name.lower()), None)
    base = target.matrix_world @ V((0, 0, 1.4)) if target else V((0, 0, 1.4))
    cam.location = base + V((dist * 0.55, -dist * 0.95, dist * 0.45))
    direction = base - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.render.filepath = os.path.join(OUT, f"v03_{name}_threeq.png")
    bpy.ops.render.render(write_still=True)
    print("V03_SHOT", name)

print("V03_PREVIEW_DONE")
