"""Blockout concept render for the 「白昼市场角落」 environment art-test (frame #1).

Phase 0 concept-lock artifact. NOT a modeling source. Primitives only, painted
with the art-bible §2 palette, framed at a §1.5-class third-person camera and
lit by §3.2 白昼行动 daytime. Renders concept/market_corner_concept_v01.png and
saves the .blend alongside. Run headless:

  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/environment/env_market_corner/blender/blockout_concept_v01.py

COORDINATE CONVENTION: authored in Blender's native Z-up (X right, Y depth, Z up).
Camera sits at +Y looking toward -Y so the stall (y=0) is the hero, the player
(y=3) is foreground, and the distant shelter (y=-8) reads in the background.
Blender's glTF exporter converts Z-up -> Y-up on export, so this matches the
art-bible §8.6 "Y-up, -Z forward" GLB convention at export time (Phase 2+),
enforced by the env gate test then. Dimensions mirror game/scripts/main.gd.
"""
import bpy
import math
import os
import mathutils

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
RENDER_PATH = os.path.join(HERE, "concept/market_corner_concept_v01.png")
BLEND_PATH = os.path.join(HERE, "blender/blockout_concept_v01.blend")

# art-bible §2 palette (r,g,b,a)
PAL = {
    "silt_ink":    (0x17/255, 0x24/255, 0x3B/255, 1.0),
    "dusk_indigo": (0x34/255, 0x33/255, 0x5E/255, 1.0),
    "tide_teal":   (0x2F/255, 0x8C/255, 0x87/255, 1.0),
    "lichen_mint": (0x78/255, 0xC9/255, 0xA4/255, 1.0),
    "coral_clay":  (0xD8/255, 0x66/255, 0x5B/255, 1.0),
    "hearth_amber":(0xF2/255, 0xA8/255, 0x5B/255, 1.0),
    "dust_cream":  (0xE7/255, 0xD2/255, 0xA3/255, 1.0),
    "basalt":      (0x4B/255, 0x52/255, 0x68/255, 1.0),
    "bone_white":  (0xF5/255, 0xE9/255, 0xD2/255, 1.0),
    "bark_plum":   (0x5A/255, 0x3F/255, 0x58/255, 1.0),
    "warm_apricot":(0xBF/255, 0xA9/255, 0x82/255, 1.0),
}


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mat(name, color, emission=None, roughness=0.8, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = emission
        bsdf.inputs["Emission Strength"].default_value = 6.0
    return m


def assign(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def add_cube(name, size, location, mat, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    o.scale = mathutils.Vector(size)
    # NOTE: do NOT transform_apply here — in this blockout pass we keep the
    # authored location (transform_apply(scale=True) collapses location to 0 in
    # Blender 5.2, which sinks cubes to the origin). Scale is applied at export
    # time in Phase 2; the visual is identical for the concept render.
    assign(o, mat)
    return o


def add_cyl(name, radius, depth, location, mat, vertices=20, rotation=(0, 0, 0)):
    # Default cylinder axis = Z (vertical) -> correct for posts/stems in Z-up.
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=vertices,
                                        location=location, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    assign(o, mat)
    return o


def add_sphere(name, radius, location, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=20, ring_count=12)
    o = bpy.context.active_object
    o.name = name
    bpy.ops.object.shade_smooth()
    assign(o, mat)
    return o


def add_capsule(name, radius, height, location, mat):
    """Vertical capsule centered at location (feet near location.z - height/2)."""
    body_h = max(height - 2 * radius, 0.01)
    z = location[2]
    add_cyl(name + "_body", radius, body_h, (location[0], location[1], z), mat, vertices=16)
    add_sphere(name + "_top", radius, (location[0], location[1], z + body_h / 2), mat)
    add_sphere(name + "_bot", radius, (location[0], location[1], z - body_h / 2), mat)


def add_prism(name, size, location, mat, yaw_deg):
    """Triangular prism roof (折片/风帆): triangle in XZ (width, height), extruded in Y (depth)."""
    w, h, d = size
    hw = w / 2.0
    verts = [
        (-hw, -d / 2, 0), (hw, -d / 2, 0), (0, -d / 2, h),
        (-hw,  d / 2, 0), (hw,  d / 2, 0), (0,  d / 2, h),
    ]
    faces = [(0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (0, 2, 5, 3)]
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    o.location = location
    o.rotation_euler = (0, 0, math.radians(yaw_deg))
    assign(o, mat)
    return o


def build_ground():
    add_cube("Ground", (28, 28, 0.5), (0, 0, -0.25), make_mat("m_ground", PAL["dust_cream"], roughness=0.95))
    add_cube("EdgeRockA", (5, 7, 0.8), (-10, -3, -0.1), make_mat("m_edgeA", PAL["dusk_indigo"], roughness=0.95))
    add_cube("EdgeRockB", (4, 6, 0.7), (10, 2, -0.05), make_mat("m_edgeB", PAL["basalt"], roughness=0.95))


def build_path():
    m = make_mat("m_path", PAL["bone_white"], roughness=0.9)
    for (y, w) in [(2.0, 3.0), (3.6, 3.4), (5.2, 3.8)]:
        add_cube(f"Path_{y}", (w, 1.6, 0.02), (0, y, 0.011), m)


def build_stall(origin):
    ox, oy, oz = origin  # oz = up
    post_mat = make_mat("m_post", PAL["bark_plum"], roughness=0.7)
    for x in (-1.6, 1.6):
        for y in (-1.15, 1.15):
            add_cyl(f"Post_{x}_{y}", 0.09, 2.7, (ox + x, oy + y, oz + 1.35), post_mat, vertices=12)
    add_prism("Canopy", (4.2, 1.0, 3.1), (ox, oy, oz + 2.72),
              make_mat("m_canopy", PAL["coral_clay"], roughness=0.6), yaw_deg=90)
    add_cube("Counter", (3.2, 0.9, 0.22), (ox, oy, oz + 0.92),
             make_mat("m_counter", PAL["dust_cream"], roughness=0.75))
    add_cube("CounterFront", (3.2, 0.08, 0.62), (ox, oy + 0.46, oz + 0.61),
             make_mat("m_counterfront", PAL["tide_teal"], roughness=0.7))
    add_cube("Shelf", (2.6, 0.5, 0.08), (ox, oy - 0.5, oz + 1.35),
             make_mat("m_shelf", PAL["bark_plum"], roughness=0.8))
    token_mat = make_mat("m_token", PAL["lichen_mint"], roughness=0.5)
    for i, dx in enumerate((-0.9, -0.3, 0.3, 0.9)):
        add_sphere(f"Token_{i}", 0.16, (ox + dx, oy + 0.1, oz + 1.13), token_mat)
    knot_mat = make_mat("m_knot", PAL["hearth_amber"], roughness=0.7)
    for y in (-1.15, 1.15):
        add_cube(f"Knot_{y}", (0.16, 0.16, 0.16), (ox + 1.6, oy + y, oz + 1.6), knot_mat)


def build_lanterns():
    m_stem = make_mat("m_lstem", PAL["silt_ink"], roughness=0.8)
    m_bulb = make_mat("m_lbulb", PAL["hearth_amber"], emission=PAL["hearth_amber"], roughness=0.5)
    for (x, y) in [(-3.2, 2.2), (3.2, 0.2)]:
        add_cyl("LanternStem", 0.06, 1.7, (x, y, 0.85), m_stem, vertices=10)
        add_sphere("LanternBulb", 0.22, (x, y, 1.82), m_bulb)


def build_glowplants():
    m_stem = make_mat("m_gstem", PAL["tide_teal"], roughness=0.8)
    m_bulb = make_mat("m_gbulb", PAL["lichen_mint"], emission=PAL["lichen_mint"], roughness=0.5)
    for i, (x, y) in enumerate([(-3.8, -1.2), (3.8, 2.6), (-2.6, 3.8), (2.6, -2.8)]):
        add_cyl(f"GStem_{i}", 0.05, 1.25, (x, y, 0.55), m_stem, vertices=8)
        add_sphere(f"GBulb_{i}", 0.22, (x, y, 1.18), m_bulb)


def build_rocks():
    m = make_mat("m_rock", PAL["basalt"], roughness=0.95)
    add_cube("RockL", (4.0, 3.5, 1.6), (-7.5, -3.0, 0.6), m)
    add_cube("RockR", (3.0, 3.0, 1.3), (7.0, 1.5, 0.45), m)


def build_shelter_distant():
    # background nav-point beyond the stall (camera looks -Y, so negative Y = far)
    loc = (-1.5, -8.0, 0.0)
    add_cube("ShelterBody", (4.5, 3.6, 2.8), (loc[0], loc[1], 1.4),
             make_mat("m_shelter", PAL["dusk_indigo"], roughness=0.9))
    add_prism("ShelterRoof", (4.8, 1.6, 3.8), (loc[0], loc[1], 3.4),
              make_mat("m_shelterroof", PAL["bark_plum"], roughness=0.9), yaw_deg=90)
    add_cube("ShelterWindow", (0.9, 0.1, 0.9), (loc[0] + 1.3, loc[1] + 1.8, 1.7),
             make_mat("m_shelterwin", PAL["hearth_amber"], emission=PAL["hearth_amber"], roughness=0.5))


def build_characters():
    # feet near z=0: capsule center z = body_h/2 + r
    pz, mz = 0.75, 0.75
    add_capsule("Player", 0.34, 1.5, (2.3, 3.0, pz), make_mat("m_player", PAL["warm_apricot"], roughness=0.8))
    add_sphere("PlayerHead", 0.3, (2.3, 3.0, pz + 0.95), make_mat("m_phead", PAL["warm_apricot"], roughness=0.8))
    add_capsule("Mira", 0.36, 1.5, (-1.9, 1.7, mz), make_mat("m_mira", PAL["coral_clay"], roughness=0.8))
    add_sphere("MiraHead", 0.3, (-1.9, 1.7, mz + 0.95), make_mat("m_mirahead", PAL["coral_clay"], roughness=0.8))


def build_lighting():
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
    fill.data.color = PAL["tide_teal"][:3]

    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.90, 0.86, 0.78, 1.0)  # warm pale daytime sky
    bg.inputs["Strength"].default_value = 1.1


def build_camera():
    # third-person ~6 m back along +Y, lens 30 mm (hFOV ~62°, close to §1.5 68°)
    bpy.ops.object.camera_add(location=(0.0, 7.0, 1.75))
    cam = bpy.context.active_object
    cam.name = "ArtTestCam"
    cam.data.lens = 30.0
    focus = mathutils.Vector((0.0, -0.5, 1.0))
    direction = focus - cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = cam


def render():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1440
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = RENDER_PATH
    scene.eevee.taa_render_samples = 64
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.render.render(write_still=True)


def main():
    os.makedirs(os.path.dirname(RENDER_PATH), exist_ok=True)
    reset_scene()
    build_ground()
    build_path()
    build_stall((0.0, 0.0, 0.0))
    build_lanterns()
    build_glowplants()
    build_rocks()
    build_shelter_distant()
    build_characters()
    build_lighting()
    build_camera()
    render()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print("BLOCKOUT_CONCEPT_DONE render=%s blend=%s" % (RENDER_PATH, BLEND_PATH))


if __name__ == "__main__":
    main()
