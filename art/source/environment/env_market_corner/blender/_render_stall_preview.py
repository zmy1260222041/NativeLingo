"""Render a preview of env_market_stall_a.glb at a §1.5-class third-person
camera with §3.2 daytime lighting, for Phase 2 visual quality check.
Run headless. Temporary artifact — not part of the asset lock.
"""
import bpy
import math
import mathutils
import os

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
GLB = os.path.join(HERE, "export/env_market_stall_a.glb")
OUT = os.path.join(HERE, "concept/stall_preview_v01.png")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

# §3.2 白昼行动: warm bone-white key + tide-teal bounce; warm pale sky
bpy.ops.object.light_add(type='SUN', location=(0, 0, 0))
sun = bpy.context.active_object
sun.name = "Sun"
sun.rotation_euler = (math.radians(45), math.radians(25), math.radians(20))
sun.data.energy = 3.8
sun.data.color = (1.0, 0.96, 0.88)
sun.data.angle = math.radians(1.5)

bpy.ops.object.light_add(type='SUN', location=(0, 0, 0))
fill = bpy.context.active_object
fill.name = "TealBounce"
fill.rotation_euler = (math.radians(-40), 0, math.radians(200))
fill.data.energy = 0.6
fill.data.color = (0x2F/255, 0x8C/255, 0x87/255)

world = bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (0.90, 0.86, 0.78, 1.0)
bg.inputs["Strength"].default_value = 1.1

# §1.5-class third person: stall front faces +Y in Blender (GLB -Z -> Blender +Y)
bpy.ops.object.camera_add(location=(0.0, 7.0, 1.75))
cam = bpy.context.active_object
cam.name = "StallCam"
cam.data.lens = 30.0
focus = mathutils.Vector((0.0, -0.5, 1.4))
direction = focus - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1440
scene.render.resolution_y = 900
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = OUT
scene.eevee.taa_render_samples = 64
scene.view_settings.view_transform = 'Standard'
bpy.ops.render.render(write_still=True)
print("STALL_PREVIEW_DONE " + OUT)
