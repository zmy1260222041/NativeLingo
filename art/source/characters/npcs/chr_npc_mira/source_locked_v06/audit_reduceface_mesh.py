"""Mesh-integrity audit of the ReduceFace Mira output — quantify holes, not vibes.

ReduceFace (Polygen) is a DECIMATION tool. Mira's Hunyuan high-poly has many thin features
(accessories, 3-finger gaps, harness) + was 2087 connected components; aggressive reduction
can collapse thin geometry into holes/missing faces. This script counts boundary edges
(open holes), groups them into loops, locates each loop by body region, and reports
non-manifold / components. Also renders backface-culled views so holes are visible.
"""
from pathlib import Path
import bpy, bmesh
from mathutils import Vector

V06 = Path("/Users/a86138/Developer/NativeLingo/art/source/characters/npcs/chr_npc_mira/source_locked_v06")
GLB = V06 / "cloud_raw/reduceface_high_01.glb"
OUT = V06 / "validation"

bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(GLB))
objs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
lod = objs[0]
bm = bmesh.new(); bm.from_mesh(lod.data); bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table()

nverts, nfaces = len(bm.verts), len(bm.faces)
boundary = [e for e in bm.edges if e.is_boundary]            # 1 face → open hole edge
nonmanifold = [e for e in bm.edges if not e.is_manifold]      # !=2 faces
# connected components (verts)
seen=set(); comps=0
for v in bm.verts:
    if v.index in seen: continue
    comps+=1; st=[v]; seen.add(v.index)
    while st:
        c=st.pop()
        for e in c.link_edges:
            o=e.other_vert(c)
            if o.index not in seen: seen.add(o.index); st.append(o)

# group boundary edges into loops (walk via shared boundary verts) — use stable indices
loops = []
used = set()  # edge indices
verts_to_boundary = {v.index: [] for v in bm.verts}
for e in boundary:
    for v in e.verts:
        verts_to_boundary[v.index].append(e)
for e in boundary:
    if e.index in used:
        continue
    loop = [e]; used.add(e.index); stack = [e]
    while stack:
        cur = stack.pop()
        for v in cur.verts:
            for nb in verts_to_boundary[v.index]:
                if nb.index not in used:
                    used.add(nb.index); loop.append(nb); stack.append(nb)
    loops.append(loop)

# locate each loop centroid by body region (fraction of height)
pts=[lod.matrix_world @ v.co for v in bm.verts]
mn=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)))
mx=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
h=mx.z-mn.z
def region(e):
    c=lod.matrix_world @ e.verts[0].co
    frac=(c.z-mn.z)/h if h else 0
    xabs=abs(c.x)
    if frac>0.86: rz="head/face"
    elif frac>0.78: rz="neck"
    elif frac>0.45 and xabs<0.18: rz="torso"
    elif frac>0.30 and xabs>=0.18: rz="arm/hand"
    elif frac>0.30: rz="hip"
    elif frac>0.12: rz="lower_leg"
    else: rz="foot"
    return rz
from collections import Counter
loop_sizes=sorted([len(l) for l in loops], reverse=True)
loop_regions=Counter()
loop_centroids=[]
for l in loops:
    cc = sum(((lod.matrix_world @ e.verts[0].co) for e in l), Vector((0, 0, 0))) / max(1, len(l))
    loop_regions[region(l[0])]+=1
    loop_centroids.append(cc)

print("AUDIT tris=%d verts=%d"%(nfaces,nverts))
print("AUDIT boundary_edges(open holes)=%d  non_manifold=%d  components=%d"%(len(boundary),len(nonmanifold),comps))
print("AUDIT boundary_loops=%d  top_sizes=%s"%(len(loops), loop_sizes[:15]))
print("AUDIT holes_by_region=%s"%dict(loop_regions))
print("AUDIT input_for_compare: Hunyuan high-poly was 2087 components / 108488 non-manifold edges")

# render backface-culled front+back so holes show as gaps
scene=bpy.context.scene
scene.render.engine="BLENDER_WORKBENCH"
scene.render.film_transparent=True
scene.render.image_settings.file_format="PNG"; scene.render.image_settings.color_mode="RGBA"
sh=scene.display.shading
sh.light="STUDIO"; sh.color_type="SINGLE"; sh.single_color=(0.66,0.63,0.59)
sh.show_cavity=True; sh.cavity_type="BOTH"; sh.show_backface_culling=True
sh.background_type="VIEWPORT"; sh.background_color=(0.03,0.03,0.04)
center=(mn+mx)*0.5
def addcam(name,loc,tgt,ortho=True,scale=1.0):
    d=bpy.data.cameras.new(name); d.type="ORTHO"; d.ortho_scale=scale; d.clip_start=0.01; d.clip_end=50
    c=bpy.data.objects.new(name,d); scene.collection.objects.link(c); c.location=loc
    c.rotation_euler=(Vector(tgt)-Vector(loc)).to_track_quat("-Z","Y").to_euler(); return c
for tag,off in [("front",(0,-1,0)),("back",(0,1,0)),("side",(1,0,0))]:
    cam=addcam("c_"+tag, center+Vector(off)*h*2.4, center, scale=h*0.62)
    scene.camera=cam; scene.render.resolution_x=768; scene.render.resolution_y=768
    scene.render.filepath=str(OUT/f"rf_holes_{tag}.png"); bpy.ops.render.render(write_still=True)
# wireframe too
lod.display_type="WIRE"; sh.show_backface_culling=False
cam=addcam("c_w", center+Vector((0,-1,0))*h*2.4, center, scale=h*0.62)
scene.camera=cam; scene.render.resolution_x=900; scene.render.resolution_y=900
scene.render.filepath=str(OUT/"rf_holes_wire.png"); bpy.ops.render.render(write_still=True)
bm.free()
print("AUDIT_DONE")
