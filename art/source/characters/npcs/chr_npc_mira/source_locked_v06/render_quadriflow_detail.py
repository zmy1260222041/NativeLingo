"""Render detail close-ups of a Quadriflow LOD0 to assess face/hand quality.

Version-driven: set QF_VER=v02 (etc). Opens retopo/chr_npc_mira_lod0_quadriflow_<VER>.blend,
renders head close-ups (4 angles), a hand close-up, a full-body wireframe, and (for v01) hipoly
head comparisons. Solid + smooth + cavity shading (most honest for geometry quality).
"""
import os
from pathlib import Path
import bpy
from mathutils import Vector

VER = os.environ.get("QF_VER", "v01")
V06 = Path("/Users/a86138/Developer/NativeLingo/art/source/characters/npcs/chr_npc_mira/source_locked_v06")
BLEND = V06 / "retopo" / f"chr_npc_mira_lod0_quadriflow_{VER}.blend"
OUT = V06 / "validation"
OUT.mkdir(parents=True, exist_ok=True)
PFX = f"qf_detail_{VER}"

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
lod = bpy.data.objects.get(f"MIRA_lod0_quadriflow_{VER}")
hipoly = bpy.data.objects.get("MIRA_hipoly_ref")
assert lod, f"no MIRA_lod0_quadriflow_{VER} in {BLEND}"

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
sh = scene.display.shading
sh.light = "STUDIO"; sh.color_type = "SINGLE"; sh.single_color = (0.66, 0.63, 0.59)
sh.show_cavity = True; sh.cavity_type = "BOTH"; sh.show_object_outline = False
sh.background_type = "VIEWPORT"; sh.background_color = (0.06, 0.06, 0.07)

def smooth_on(obj):
    for p in obj.data.polygons: p.use_smooth = True
smooth_on(lod)
if hipoly: smooth_on(hipoly)

def reveal(obj):
    for o in bpy.data.objects:
        if o.type == "MESH": o.hide_render = (o is not obj)

def add_cam(name, loc, target, lens=85, ortho=False, scale=0.5):
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO" if ortho else "PERSP"; data.lens = lens
    if ortho: data.ortho_scale = scale
    data.clip_start = 0.01; data.clip_end = 50.0
    cam = bpy.data.objects.new(name, data); scene.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return cam

def render(cam, path, res=768):
    scene.render.resolution_x = res; scene.render.resolution_y = res
    scene.camera = cam; scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)

head_c = Vector((0, 0, 1.58)); d = 0.55
for tag, off in [("pY",(0,d,0)),("nY",(0,-d,0)),("pX",(d,0,0)),("nX",(-d,0,0))]:
    reveal(lod)
    render(add_cam(f"C_h_{tag}", head_c+Vector(off), head_c), OUT/f"{PFX}_head_{tag}.png")

hand_c = Vector((0.33, 0.0, 0.95))
reveal(lod)
render(add_cam("C_hand", hand_c+Vector((0.25,-0.25,0.05)), hand_c), OUT/f"{PFX}_hand.png")

reveal(lod); lod.display_type = "WIRE"
render(add_cam("C_wire", Vector((0,0,0.86))+Vector((0,-3.0,0)), Vector((0,0,0.86)), ortho=True, scale=1.0),
      OUT/f"{PFX}_wireframe_full.png", res=900)
lod.display_type = "TEXTURED"

if VER == "v01" and hipoly:  # hipoly comparison only needed once
    for tag, off in [("pY",(0,d,0)),("nY",(0,-d,0)),("pX",(d,0,0)),("nX",(-d,0,0))]:
        reveal(hipoly)
        render(add_cam(f"C_hh_{tag}", head_c+Vector(off), head_c), OUT/f"{PFX}_hipoly_head_{tag}.png")

print("DETAIL_DONE", VER, OUT)
