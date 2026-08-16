"""Render detail close-ups of the ai3d ReduceFace (Polygen) Mira LOD for A/B vs Quadriflow.

Imports cloud_raw/reduceface_high_01.glb (solid+cavity, same style as the Quadriflow detail
renders) and also re-attaches the baked PNG (reduceface_high_02.bin) for a textured view.
"""
from pathlib import Path
import bpy
from mathutils import Vector

V06 = Path("/Users/a86138/Developer/NativeLingo/art/source/characters/npcs/chr_npc_mira/source_locked_v06")
GLB = V06 / "cloud_raw/reduceface_high_01.glb"
TEX = V06 / "cloud_raw/reduceface_high_02.bin"  # actually a PNG
OUT = V06 / "validation"
OUT.mkdir(parents=True, exist_ok=True)
PFX = "qf_detail_rf"

bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(GLB))
objs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
assert objs, "no mesh imported"
for o in objs:
    o.hide_render = False; o.hide_viewport = False; o.hide_set(False); o.display_type = "TEXTURED"
lod = objs[0]
print("RF_IMPORT", len(objs), "mesh(es); uv_layers:", [uv.name for uv in lod.data.uv_layers], "verts", len(lod.data.vertices))

# bounds
pts = [lod.matrix_world @ Vector(c) for c in lod.bound_box]
mn = Vector(tuple(min(p[a] for p in pts) for a in range(3)))
mx = Vector(tuple(max(p[a] for p in pts) for a in range(3)))
print("RF_BOUNDS", [round(x,3) for x in mn], "->", [round(x,3) for x in mx], "h=", round(mx.z-mn.z,3))

for p in lod.data.polygons:
    p.use_smooth = True

# attach baked texture if UVs exist
tex_img = None
if lod.data.uv_layers:
    try:
        tex_img = bpy.data.images.load(str(TEX))
        mat = bpy.data.materials.new("rf_baked")
        mat.use_nodes = True
        nt = mat.node_tree
        for n in list(nt.nodes): nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial"); bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = tex_img
        nt.links.new(tex.outputs[0], bsdf.inputs["Base Color"])
        nt.links.new(bsdf.outputs[0], out.inputs[0])
        if lod.data.materials: lod.data.materials[0] = mat
        else: lod.data.materials.append(mat)
        print("RF_TEX attached", tex_img.name, tex_img.size)
    except Exception as e:
        print("RF_TEX attach failed:", e); tex_img = None

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"; scene.render.image_settings.color_mode = "RGBA"
sh = scene.display.shading
sh.light = "STUDIO"; sh.color_type = "SINGLE"; sh.single_color = (0.66, 0.63, 0.59)
sh.show_cavity = True; sh.cavity_type = "BOTH"; sh.show_object_outline = False
sh.background_type = "VIEWPORT"; sh.background_color = (0.06, 0.06, 0.07)

height = mx.z - mn.z
center = (mn + mx) * 0.5
head_c = Vector((center.x, center.y, mx.z - height * 0.07))
hand_c = Vector((mx.x * 0.80, center.y, mn.z + height * 0.50))
d = height * 0.32  # camera distance scaled to actual model size

def add_cam(name, loc, target, lens=85, ortho=False, scale=0.5):
    dd = bpy.data.cameras.new(name); dd.type = "ORTHO" if ortho else "PERSP"; dd.lens = lens
    if ortho: dd.ortho_scale = scale
    dd.clip_start = 0.01; dd.clip_end = 50.0
    c = bpy.data.objects.new(name, dd); scene.collection.objects.link(c)
    c.location = loc; c.rotation_euler = (Vector(target)-Vector(loc)).to_track_quat("-Z","Y").to_euler()
    return c

def render(cam, path, res=768, material=False):
    sh.color_type = "MATERIAL" if material else "SINGLE"
    scene.render.resolution_x = res; scene.render.resolution_y = res
    scene.camera = cam; scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)

# full front (orient / locate face & hands)
render(add_cam("front", center + Vector((0, -height*2.6, 0)), center, ortho=True, scale=height*0.62),
      OUT/f"{PFX}_front.png", res=820)
for tag, off in [("pY",(0,d,0)),("nY",(0,-d,0)),("pX",(d,0,0)),("nX",(-d,0,0))]:
    render(add_cam(f"h_{tag}", head_c+Vector(off), head_c), OUT/f"{PFX}_head_{tag}.png")
render(add_cam("hand", hand_c + Vector((0.22, -0.22, 0.03)), hand_c), OUT/f"{PFX}_hand.png")
lod.display_type = "WIRE"
render(add_cam("wire", center + Vector((0, -height*2.6, 0)), center, ortho=True, scale=height*0.62),
      OUT/f"{PFX}_wireframe_full.png", res=900)
lod.display_type = "TEXTURED"
print("RF_DETAIL_DONE", PFX, "height", round(height,3))
