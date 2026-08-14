"""Render a MarketCorner composition preview from the exported env GLBs.

Imports every Phase 2/4 GLB at its MarketCorner layout position, frames a
§1.5-class third-person camera, lights with §3.2 白昼行动, and renders
1440x900 for visual review. Temporary artifact (not part of the asset lock).
"""
import bpy
import math
import mathutils
import os

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
GLB_DIR = os.path.join(HERE, "export")
OUT = os.path.join(HERE, "concept/market_corner_composite_v01.png")

# MarketCorner Godot positions -> Blender Z-up (x, y=godot_z negated, z=godot_y)
LAYOUT = [
    ("env_ground_market_a.glb",      (0.0, 0.0, 0.0)),
    ("env_market_stall_a.glb",       (-1.8, 2.2, 0.0)),
    ("prp_lantern_market_a.glb",     (-3.2, 2.2, 0.0)),
    ("prp_lantern_market_a.glb",     (3.2, 0.2, 0.0)),
    ("env_shelter_distant_a.glb",    (-7.0, -8.5, 0.0)),
    ("env_rock_market_a.glb",        (-7.5, -3.0, 0.0)),
    ("env_rock_market_b.glb",        (7.0, 1.5, 0.0)),
    ("fol_glowplant_a.glb",          (-3.8, -1.2, 0.0)),
    ("fol_glowplant_a.glb",          (3.8, 2.6, 0.0)),
    ("fol_glowplant_a.glb",          (-2.6, 3.8, 0.0)),
    ("fol_glowplant_a.glb",          (2.6, -2.8, 0.0)),
]

PAL = {
    "warm_apricot": (0xBF/255, 0xA9/255, 0x82/255, 1.0),
    "coral_clay":   (0xD8/255, 0x66/255, 0x5B/255, 1.0),
}


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def capsule(name, color, loc):
    m = bpy.data.materials.new(name + "_mat")
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.8
    bpy.ops.mesh.primitive_cylinder_add(radius=0.34, depth=1.2, vertices=14, location=(loc[0], loc[1], loc[2] + 0.35))
    body = bpy.context.active_object
    body.name = name
    body.data.materials.append(m)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(loc[0], loc[1], loc[2] + 1.1), segments=16, ring_count=10)
    head = bpy.context.active_object
    head.name = name + "_head"
    head.data.materials.append(m)


def main():
    reset_scene()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for file, loc in LAYOUT:
        bpy.ops.import_scene.gltf(filepath=os.path.join(GLB_DIR, file))
        # move the imported root(s) to their layout position
        for obj in bpy.context.selected_objects:
            obj.location = mathutils.Vector(loc)
    capsule("Player", PAL["warm_apricot"], (2.3, -3.0, 0.0))
    capsule("Mira", PAL["coral_clay"], (-3.0, 2.0, 1.0))

    # §3.2 白昼行动 lighting
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

    # §1.5-class camera: stall front faces +Y in Blender, camera sits at +Y
    bpy.ops.object.camera_add(location=(0.0, 7.0, 1.75))
    cam = bpy.context.active_object
    cam.name = "ArtTestCam"
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
    print("MARKET_PREVIEW_DONE " + OUT)


if __name__ == "__main__":
    main()
