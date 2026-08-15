"""Render validation stills of the alien-green kit GLBs."""
import os
import bpy
import mathutils

REPO = "/Users/a86138/Developer/NativeLingo"
EXPORT = os.path.join(REPO, "art/source/environment/env_market_corner/export")
OUT = os.path.join(REPO, "art/source/environment/env_market_corner/validation")

bpy.ops.wm.read_factory_settings(use_empty=True)
for name in ("fol_frond_alien_a", "fol_reed_glow_a", "prp_monolith_a"):
    bpy.ops.import_scene.gltf(filepath=os.path.join(EXPORT, name + ".glb"))

world = bpy.data.worlds.new("World")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.72, 0.78, 0.9, 1.0)
bg.inputs[1].default_value = 1.4
bpy.context.scene.world = world

key = bpy.data.lights.new("Key", "SUN")
key.energy = 3.0
key_obj = bpy.data.objects.new("Key", key)
key_obj.rotation_euler = (0.9, 0.2, 0.7)
bpy.context.collection.objects.link(key_obj)

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 50
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam

bpy.context.scene.render.resolution_x = 900
bpy.context.scene.render.resolution_y = 700
bpy.context.scene.render.engine = "BLENDER_EEVEE"
bpy.context.scene.render.image_settings.file_format = "PNG"

V = mathutils.Vector
# lay the three kits out in a row so one frame shows all
offsets = {"frond": -2.2, "reed_glow": 0.0, "monolith": 2.6}
moved = 0
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    lower = obj.name.lower()
    if "lod1__" in lower or "lod2__" in lower:
        obj.hide_render = True
        obj.hide_viewport = True
        continue
    for token, ox in offsets.items():
        if token in lower:
            obj.location.x += ox
            moved += 1
            break

cam.location = V((0.2, -4.8, 1.6))
direction = V((0.0, 0.7, 0.8)) - cam.location
cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.render.filepath = os.path.join(OUT, "v03_alien_greens_row.png")
bpy.ops.render.render(write_still=True)
print("GREEN_PREVIEW_DONE moved=", moved)
