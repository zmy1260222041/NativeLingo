"""Deterministic, isolated Blender asset build/bake/export support.

Only output in this version directory and explicitly named game assets is owned.
High and low meshes stay in separate collections inside each packed .blend.
"""
from pathlib import Path
import json
import math
import hashlib
import bpy
import bmesh
import numpy as np
from mathutils import Vector

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
GAME = ROOT / 'game/assets/environment'


def clean():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0


def color(hex_color):
    rgb = [int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v < .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb) + (1,)


def material(name, hex_color, rough=.8, metal=0, grain=.006):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = color(hex_color)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    tex = nodes.new('ShaderNodeTexNoise')
    coordinates=nodes.new('ShaderNodeTexCoord')
    links.new(coordinates.outputs['Object'],tex.inputs['Vector'])
    tex.inputs['Scale'].default_value = 24
    tex.inputs['Detail'].default_value = 1
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .10
    bump.inputs['Distance'].default_value = grain
    links.new(tex.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    # Small roughness variation is material structure, not dirt sprayed everywhere.
    remap=nodes.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value=max(.30,rough-.045)
    remap.inputs['To Max'].default_value=min(1,rough+.025)
    links.new(tex.outputs['Fac'],remap.inputs['Value'])
    links.new(remap.outputs['Result'],bsdf.inputs['Roughness'])
    return mat


def mesh(name, verts, faces, mat, smooth=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    if mat:
        data.materials.append(mat)
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    for face in data.polygons:
        face.use_smooth = smooth
    return obj


def lathe(name, profile, center, mat, segments=32, oval=(1, 1), smooth=True):
    """Continuous closed cross-section: (radius, height), including the opening."""
    verts, faces = [], []
    for radius, z in profile:
        for i in range(segments):
            a = i * math.tau / segments
            verts.append((center[0]+radius*math.cos(a)*oval[0], center[1]+radius*math.sin(a)*oval[1], center[2]+z))
    for j in range(len(profile)-1):
        for i in range(segments):
            a = j*segments+i
            b = j*segments+(i+1)%segments
            faces.append((a,b,b+segments,a+segments))
    faces.append(tuple(reversed(range(segments))))
    faces.append(tuple((len(profile)-1)*segments+i for i in range(segments)))
    return mesh(name,verts,faces,mat,smooth)


def slab(name, width, depth, bottom, top, center, mat, cut=.02):
    # Authored narrow fired-clay edge, not a global bevel modifier.
    verts=[]
    for z, inset in [(bottom,cut),(bottom+cut,0),(top-cut,0),(top,cut)]:
        for x,y in [(-width/2+inset,-depth/2+inset),(width/2-inset,-depth/2+inset),(width/2-inset,depth/2-inset),(-width/2+inset,depth/2-inset)]:
            verts.append((x+center[0],y+center[1],z))
    faces=[(3,2,1,0),(12,13,14,15)]
    for j in range(3):
        for i in range(4):
            faces.append((j*4+i,j*4+(i+1)%4,(j+1)*4+(i+1)%4,(j+1)*4+i))
    return mesh(name,verts,faces,mat)


def tube(name, points, radii, mat, sides=10):
    """Connected profile loops, seated endpoints; no disconnected cylinders."""
    verts,faces=[],[]
    previous_axis=None
    for j,point in enumerate(points):
        p=Vector(point)
        tangent=Vector(points[min(j+1,len(points)-1)])-Vector(points[max(j-1,0)])
        tangent.normalize()
        axis=tangent.cross(Vector((0,0,1))) if previous_axis is None else previous_axis-tangent*previous_axis.dot(tangent)
        if axis.length<.01: axis=tangent.cross(Vector((1,0,0)))
        axis.normalize()
        previous_axis=axis.copy()
        other=tangent.cross(axis).normalized()
        for i in range(sides):
            a=math.tau*i/sides
            verts.append(tuple(p+radii[j]*(math.cos(a)*axis+math.sin(a)*other)))
    for j in range(len(points)-1):
        for i in range(sides):
            faces.append((j*sides+i,j*sides+(i+1)%sides,(j+1)*sides+(i+1)%sides,(j+1)*sides+i))
    faces.extend([tuple(reversed(range(sides))),tuple((len(points)-1)*sides+i for i in range(sides))])
    return mesh(name,verts,faces,mat,True)


def bounds(obj):
    v=[obj.matrix_world@Vector(c) for c in obj.bound_box]
    return [[min(p[i] for p in v) for i in range(3)],[max(p[i] for p in v) for i in range(3)]]


def join(objects,name):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    bpy.ops.object.join()
    obj=bpy.context.object
    obj.name=name
    # Bake location into geometry: every asset uses an origin at the support base.
    bpy.context.scene.cursor.location=(0,0,0)
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    return obj


def save_image(image,path):
    image.filepath_raw=str(path)
    image.file_format='PNG'
    image.save()
    # Keep standalone AO/roughness after ORM replaces their material links.
    image.use_fake_user=True
    image.pack()


def bake_asset(stem, objects, size, extra_high=None, lod=True, samples=16):
    """Selected-to-active Cycles projection; never bake direct lighting to color."""
    asset_dir=OUT/stem
    manifest=json.loads((ROOT/'art/source/environment/ASSET_LOCK_MANIFEST.json').read_text())
    target=str((asset_dir/(stem+'.blend')).relative_to(ROOT))
    assert not any(item['path']==target for asset in manifest['assets'] for item in asset['files']), 'Create a new version before rebuilding a locked source'
    asset_dir.mkdir(parents=True,exist_ok=True)
    low=join(objects, 'lod0__'+stem)
    before=len(low.data.vertices)
    high=low.copy()
    high.data=low.data.copy()
    bpy.context.collection.objects.link(high)
    high.name='HIGH__'+stem
    # SIMPLE densifies source while preserving the authored shape and contacts.
    modifier=high.modifiers.new('source_detail_sampling','SUBSURF')
    modifier.subdivision_type='SIMPLE'
    modifier.levels=2
    sources=[high]+(extra_high or [])
    for o in sources: o.hide_render=False
    bpy.ops.object.select_all(action='DESELECT')
    low.select_set(True)
    bpy.context.view_layer.objects.active=low
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.018)
    bpy.ops.object.mode_set(mode='OBJECT')
    # Tangent-space bake and glTF export use the exact same triangulation.
    tri=low.modifiers.new('bake_export_triangulation','TRIANGULATE')
    bpy.ops.object.modifier_apply(modifier=tri.name)
    # Colors are on the high source; no vertex tint should multiply the baked map.
    for attr in list(low.data.color_attributes): low.data.color_attributes.remove(attr)
    target=bpy.data.materials.new('mat_finish_'+stem)
    target.use_nodes=True
    low.data.materials.clear()
    low.data.materials.append(target)
    node=target.node_tree.nodes.new('ShaderNodeTexImage')
    target.node_tree.nodes.active=node
    for p in low.data.polygons: p.material_index=0
    scene=bpy.context.scene
    scene.render.engine='CYCLES'
    scene.cycles.samples=samples
    scene.render.bake.use_selected_to_active=True
    scene.render.bake.cage_extrusion=.028
    scene.render.bake.max_ray_distance=.07
    scene.render.bake.margin=max(8,size//128)
    scene.render.bake.use_clear=True
    scene.render.bake.use_pass_direct=False
    scene.render.bake.use_pass_indirect=False
    scene.render.bake.use_pass_color=True
    images={}
    for label,bake_type,default in [('base_color','DIFFUSE',(.2,.2,.2,1)),('normal','NORMAL',(.5,.5,1,1)),('ao','AO',(1,1,1,1)),('roughness','ROUGHNESS',(1,1,1,1))]:
        image=bpy.data.images.new(stem+'_'+label,width=size,height=size,alpha=False)
        image.generated_color=default
        image.colorspace_settings.name='sRGB' if label=='base_color' else 'Non-Color'
        node.image=image
        bpy.ops.object.select_all(action='DESELECT')
        for o in sources: o.select_set(True)
        low.select_set(True)
        bpy.context.view_layer.objects.active=low
        bpy.ops.object.bake(type=bake_type)
        save_image(image,asset_dir/(stem+'_'+label+'.png'))
        images[label]=image
        print('BAKED',stem,label,flush=True)
    # Metallic is baked through emission, not inferred from pixel hue.
    old_links=[]
    for mat in {m for o in sources for m in o.data.materials if m}:
        nodes,links=mat.node_tree.nodes,mat.node_tree.links
        output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
        original=output.inputs['Surface'].links[0].from_socket
        bsdf=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
        emission=nodes.new('ShaderNodeEmission')
        value=bsdf.inputs['Metallic'].default_value
        emission.inputs['Color'].default_value=(value,value,value,1)
        links.new(emission.outputs[0],output.inputs['Surface'])
        old_links.append((mat,output,original,emission))
    metal=bpy.data.images.new(stem+'_metallic',width=size,height=size,alpha=False)
    metal.colorspace_settings.name='Non-Color'
    node.image=metal
    bpy.ops.object.bake(type='EMIT')
    for mat,output,original,emission in old_links:
        mat.node_tree.links.new(original,output.inputs['Surface'])
        mat.node_tree.nodes.remove(emission)
    pixels=np.ones(size*size*4,dtype=np.float32).reshape((-1,4))
    for channel,image in [(0,images['ao']),(1,images['roughness']),(2,metal)]:
        data=np.empty(size*size*4,dtype=np.float32)
        image.pixels.foreach_get(data)
        pixels[:,channel]=data.reshape((-1,4))[:,0]
    orm=bpy.data.images.new(stem+'_orm',width=size,height=size,alpha=False)
    orm.colorspace_settings.name='Non-Color'
    orm.pixels.foreach_set(pixels.ravel())
    save_image(orm,asset_dir/(stem+'_orm.png'))
    images['orm']=orm
    # Plain Principled + baked maps exports portably to glTF/Godot.
    nodes,links=target.node_tree.nodes,target.node_tree.links
    bsdf=nodes.get('Principled BSDF')
    node.image=images['base_color']
    links.new(node.outputs['Color'],bsdf.inputs['Base Color'])
    normal_tex=nodes.new('ShaderNodeTexImage'); normal_tex.image=images['normal']
    normal=nodes.new('ShaderNodeNormalMap')
    links.new(normal_tex.outputs['Color'],normal.inputs['Color'])
    links.new(normal.outputs['Normal'],bsdf.inputs['Normal'])
    orm_tex=nodes.new('ShaderNodeTexImage'); orm_tex.image=orm
    separate=nodes.new('ShaderNodeSeparateColor')
    links.new(orm_tex.outputs['Color'],separate.inputs[0])
    links.new(separate.outputs['Green'],bsdf.inputs['Roughness'])
    links.new(separate.outputs['Blue'],bsdf.inputs['Metallic'])
    # Exporter recognizes the glTF occlusion socket convention.
    group=bpy.data.node_groups.new('glTF Material Output','ShaderNodeTree')
    group.interface.new_socket(name='Occlusion',in_out='INPUT',socket_type='NodeSocketFloat')
    group_node=nodes.new('ShaderNodeGroup'); group_node.node_tree=group
    links.new(separate.outputs['Red'],group_node.inputs['Occlusion'])
    outputs=[low]
    if lod:
        for level,ratio in [(1,.55),(2,.25)]:
            obj=low.copy(); obj.data=low.data.copy()
            bpy.context.collection.objects.link(obj)
            obj.name='lod%d__'%level+stem
            dec=obj.modifiers.new('lod_silhouette','DECIMATE'); dec.ratio=ratio
            outputs.append(obj)
    for o in sources: o.hide_render=True; o.hide_set(True)
    high_collection=bpy.data.collections.new('HIGH_BAKE_SOURCES')
    scene.collection.children.link(high_collection)
    for o in sources:
        for c in list(o.users_collection): c.objects.unlink(o)
        high_collection.objects.link(o)
    bpy.ops.object.select_all(action='DESELECT')
    for o in outputs: o.select_set(True)
    bpy.context.view_layer.objects.active=low
    dest=asset_dir/(stem+'.glb')
    bpy.ops.export_scene.gltf(filepath=str(dest),export_format='GLB',use_selection=True,export_apply=True,export_animations=False,export_yup=True,export_normals=True,export_tangents=True,export_vertex_color='ACTIVE')
    for o in outputs[1:]: o.hide_render=True; o.hide_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=str(asset_dir/(stem+'.blend')))
    report={'asset':stem,'resolution':size,'selected_to_active':True,'color_contains_lighting':False,'normal_convention':'OpenGL +Y','high_subdivision':'SIMPLE 2','low_vertices':before,'contacts':getattr(bake_asset,'contacts',[]),'maps':{k:str((asset_dir/(stem+'_'+k+'.png')).relative_to(ROOT)) for k in ['base_color','normal','ao','orm']},'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}
    (asset_dir/'bake_report.json').write_text(json.dumps(report,indent=2)+'\n')
    return low,dest
