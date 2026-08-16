"""Render a preview of the textured player GLB for visual check."""
import bpy
import math
import mathutils
import os

GLB = "/Users/a86138/Developer/NativeLingo/art/source/characters/chr_player_juvenile/source_locked_v06/texture_debug/player_texture_debug.glb"
OUT = "/Users/a86138/Developer/NativeLingo/art/source/characters/chr_player_juvenile/source_locked_v06/texture_debug/preview_v01.png"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

# §3.2-style warm key light
bpy.ops.object.light_add(type='SUN', location=(0, 0, 0))
sun = bpy.context.active_object
sun.rotation_euler = (math.radians(45), math.radians(25), math.radians(20))
sun.data.energy = 3.0
sun.data.color = (1.0, 0.96, 0.88)
sun.data.angle = math.radians(1.5)

world = bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (0.90, 0.86, 0.78, 1.0)
bg.inputs["Strength"].default_value = 1.0

# front camera (character faces -Z in GLB → Blender +Y; camera at +Y)
bpy.ops.object.camera_add(location=(0.0, 3.0, 1.2))
cam = bpy.context.active_object
cam.name = "Cam"
cam.data.lens = 50.0
focus = mathutils.Vector((0.0, 0.0, 0.9))
direction = focus - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 900
scene.render.resolution_y = 1100
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = OUT
scene.eevee.taa_render_samples = 32
scene.view_settings.view_transform = 'Standard'
bpy.ops.render.render(write_still=True)
print("PLAYER_PREVIEW_DONE " + OUT)
