"""Run with Blender --background --python this_file -- [stall|food|tree|ground].

Derivative geometry uses immutable v03 GLBs, never an already-replaced runtime GLB.
Z is up in Blender; customer side is -Y (+Z in Godot).
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from asset_runner import *

BASE = OUT.parent/'export'

def imported(stem):
    bpy.ops.import_scene.gltf(filepath=str(BASE/(stem+'.glb')))
    meshes=[]
    for obj in list(bpy.data.objects):
        if obj.type!='MESH': continue
        if 'lod1' in obj.name or 'lod2' in obj.name:
            bpy.data.objects.remove(obj,do_unlink=True)
        else:
            matrix=obj.matrix_world.copy(); obj.parent=None; obj.matrix_world=matrix
            meshes.append(obj)
    return meshes

def assign(obj,mat):
    obj.data.materials.clear(); obj.data.materials.append(mat)
    for p in obj.data.polygons: p.material_index=0
    for a in list(obj.data.color_attributes): obj.data.color_attributes.remove(a)

def stall():
    clean()
    shell=material('shell_dust_rose','A77678',.88,grain=.008)
    frame=material('old_alloy_burnished','666977',.49,.62,.003)
    clay=material('ceramic_warm_ivory','BAA88C',.58,grain=.004)
    glaze=material('ceramic_glazed_edge','638A89',.42,grain=.002)
    rope=material('fiber_dark_knots','65524C',.95,grain=.01)
    under=material('shell_inner_umber','786965',.92)
    patch=material('repair_shell_celadon','798F89',.82)
    objects=[]
    for obj in imported('env_market_stall_a'):
        key=obj.name.lower()
        if any(k in key for k in ['counter','liptop','shelf','bowl','leg','rib','patch']):
            bpy.data.objects.remove(obj,do_unlink=True);continue
        assign(obj,shell if 'canopy' in key or 'frontpanel' in key else (rope if 'knot' in key else frame))
        if 'canopy' in key:
            # Baseline already has inner + outer faces. Thicken its inner skin,
            # never add a second solidify shell with coplanar overlapping rims.
            for v in obj.data.vertices:
                x,y,z=v.co
                arch=.54*(1-(abs(x)/1.6)**2) if abs(x)<=1.6 else .30*((abs(x)-1.6)/.5)**2
                eave=0 if abs(y)<=1.15 else .16*((abs(y)-1.15)/.4)**2
                if z < 2.76+arch+eave-.03: v.co.z-=.025
        objects.append(obj)
    objects.append(slab('ceramic_counter',3.28,1.10,.98,1.10,(0,0),clay,.025))
    # Ceramic edging is continuous, above four genuinely seated supports.
    objects.append(slab('glazed_customer_lip',3.28,.055,1.07,1.125,(0,-.53),glaze,.012))
    for x in [-1.36,1.36]:
        for y in [-.34,.34]:
            objects.append(tube('counter_support',[(x,y,.07),(x+.035,y,.52),(x,y,.99)],[.10,.055,.075],frame))
            objects.append(lathe('counter_foot',[(.13,.01),(.14,.04),(.10,.09)],(x,y,0),clay,16))
    objects.append(slab('counter_apron',2.65,.055,.61,.98,(0,-.31),under,.012))
    # One readable stitched repair, on the visible apron (not three arbitrary decals).
    objects.append(slab('one_mended_panel',.51,.027,.65,.89,(-.74,-.348),patch,.006))
    for x in [-.94,-.84,-.74,-.64,-.54]:
        objects.append(tube('repair_stitch',[(x,-.37,.67),(x+.012,-.378,.70)],[.008,.008],rope,6))
        objects.append(tube('repair_stitch',[(x,-.37,.84),(x+.012,-.378,.87)],[.008,.008],rope,6))
    # Arched load transfer from posts to roof, endpoints overlap by < 15mm.
    for x in [-1.6,1.6]:
        for y in [-1.15,1.15]:
            end_z=2.76+.54*(1-.86**2)-.085+.01
            objects.append(tube('seated_diagonal_brace',[(x,y,2.28),(x*.94,y*.9,2.60),(x*.86,y*.72,end_z)],[.038,.032,.038],frame,8))
    # Backstock crate with an open mouth and rim; tucked under the left counter.
    objects.append(slab('backstock_base',.62,.46,.07,.13,(-.81,.12),under,.015))
    for x in [-1.10,-.52]: objects.append(slab('backstock_side',.045,.46,.10,.49,(x,.12),shell,.008))
    for y in [-.09,.33]: objects.append(slab('backstock_wall',.62,.035,.10,.49,(-.81,y),shell,.008))
    for obj in objects:
        if obj.name.startswith('backstock'):
            for v in obj.data.vertices:v.co.z-=.052
    # The immutable Tavi anchor is behind the counter. Offset the working top,
    # supports and storage toward the customer so the NPC torso clears its back.
    for obj in objects:
        if any(obj.name.startswith(k) for k in ['ceramic_counter','glazed_customer','counter_','one_mended','repair_stitch','backstock']):
            for v in obj.data.vertices:v.co.y-=.35
    bake_asset.contacts=[{'joint':'counter_support_to_top','support_top':.99,'top_underside':.98,'overlap_m':.01},{'joint':'brace_to_roof','brace_end_z':end_z,'roof_underside_z':end_z-.01,'overlap_m':.01},{'joint':'food_to_counter','counter_top':1.10,'food_base_world_y':1.10},{'joint':'feet_to_ground','base':.01,'ground':.018,'overlap_m':.008},{'service_clear_width_m':.82,'npc_anchor_unchanged':True}]
    return bake_asset('env_market_stall_a',objects,2048)

def plate(mat):
    return lathe('hand_thrown_plate',[(.08,0),(.21,.01),(.265,.045),(.27,.06),(.255,.069),(.215,.036),(.07,.028)],(0,0,0),mat,40)

def food():
    for kind in ['burger','wrap','drink']:
        clean()
        dish=material('ceramic_celadon','758D86',.43,grain=.002)
        paper=material('unbleached_wrapper','C5B99B',.94,grain=.003)
        objects=[plate(dish)]
        if kind=='burger':
            bun=material('toasted_brioche','B98147',.78,grain=.003)
            cut=material('bun_crumb','D0AB72',.9,grain=.004)
            patty=material('charred_mushroom_patty','514235',.79,grain=.009)
            cheese=material('melted_saffron','D4A855',.57)
            leaf=material('crisp_leaf','59774E',.79)
            objects += [lathe('lower_bun',[(.13,.03),(.172,.065),(.174,.09),(.155,.105)],(0,0,0),bun),lathe('patty',[(.15,.098),(.174,.113),(.169,.143),(.14,.15)],(0,0,0),patty),lathe('upper_bun',[(.175,.178),(.18,.195),(.169,.23),(.135,.27),(.067,.29),(.005,.296)],(0,0,0),bun)]
            verts=[(0,0,.17)]+[(.187*math.cos(i*math.tau/32),.187*math.sin(i*math.tau/32),.151+.012*math.sin(i*2.7)) for i in range(32)]
            objects.append(mesh('ruffled_lettuce',verts,[(0,i+1,(i+1)%32+1) for i in range(32)],leaf,True))
            objects.append(mesh('folded_cheese',[(-.16,-.14,.158),(.16,-.14,.157),(.17,.13,.16),(-.14,.16,.156),(-.17,-.15,.142)],[(0,1,2,3),(0,4,1)],cheese))
            # Seeds are high-only shallow relief projected to the low bun.
            seed=material('sesame','DFC79A',.91)
            extra=[]
            for i in range(15):
                a=i*2.399; r=.11*math.sqrt((i+.5)/15)
                z=.296-.8*r*r
                extra.append(lathe('HIGH_sesame',[(.002,z),(.007,z+.002),(.003,z+.005)],(r*math.cos(a),r*math.sin(a),0),seed,8,oval=(.48,1)))
            bake_asset('prp_market_burger_v01',objects,512,extra_high=extra,lod=False)
        elif kind=='wrap':
            tortilla=material('toasted_flatbread','BDA47C',.91,grain=.008)
            filling=material('herb_filling','5D7150',.85)
            tomato=material('roasted_fruit','B8684E',.68)
            objects.append(lathe('rolled_flatbread',[(.055,.034),(.09,.047),(.107,.09),(.096,.148),(.07,.17)],(0,0,0),tortilla,36,oval=(1,2.05)))
            objects.append(mesh('paper_band',[(-.112,-.07,.059),(-.08,-.07,.171),(.08,-.07,.171),(.112,-.07,.059),(-.112,.07,.059),(-.08,.07,.171),(.08,.07,.171),(.112,.07,.059)],[(0,1,5,4),(1,2,6,5),(2,3,7,6)],paper))
            for i in range(6):
                objects.append(lathe('visible_cut_filling',[(.025,.07),(.031,.11),(.022,.135)],(-.045+(i%3)*.045,-.174+(i//3)*.025,0),filling if i%2 else tomato,10,oval=(1,.65)))
            bake_asset('prp_market_wrap_v01',objects,512,lod=False)
        else:
            cup=material('glazed_drink_vessel','B99877',.46,grain=.002)
            tea=material('dark_berry_drink','503D46',.34)
            objects.append(lathe('hollow_cup',[(.066,.034),(.074,.05),(.098,.265),(.097,.278),(.083,.278),(.083,.26),(.058,.064)],(0,0,0),cup,40))
            objects.append(lathe('drink_surface',[(.084,.254),(.084,.258)],(0,0,0),tea,36))
            objects.append(tube('cup_handle',[(.087,0,.215),(.155,0,.21),(.167,0,.147),(.125,0,.112),(.077,0,.13)],[.017]*5,cup,10))
            objects.append(tube('reed_straw',[(.035,.024,.20),(.04,.025,.39),(.067,.025,.425)],[.006,.006,.006],paper,8))
            bake_asset('prp_market_drink_v01',objects,512,lod=False)

def tree():
    clean()
    objects=imported('fol_tree_stranger_a')
    leaves=material('canopy_sage','71998B',.9,grain=.008)
    bark=material('bark_mauve','6D5C66',.95,grain=.014)
    for obj in objects:
        assign(obj,leaves if 'canopy' in obj.name else bark)
        for p in obj.data.polygons: p.use_smooth=True
        if 'canopy' in obj.name:
            # Retain the authored lobes but use continuous outward normals.
            bpy.context.view_layer.objects.active=obj
            obj.select_set(True)
            if obj.data.has_custom_normals:
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
            bm=bmesh.new();bm.from_mesh(obj.data)
            bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.0001)
            bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
            bm.to_mesh(obj.data);bm.free()
            for p in obj.data.polygons:p.use_smooth=True
            obj.select_set(False)
    for i in range(6):
        a=i*math.tau/6+.3
        objects.append(tube('root_flare',[(0,0,.55),(.25*math.cos(a),.25*math.sin(a),.18),(.68*math.cos(a),.68*math.sin(a),.015)],[.15,.10,.025],bark,10))
    bake_asset.contacts=[{'joint':'root_tips_to_soil','root_tip_z':.015,'terrain_z':.018,'overlap_m':.003}]
    low,path=bake_asset('fol_tree_stranger_a',objects,1024)
    # The whole connected asset sways by height; keep canopy in the node label.
    for obj in bpy.data.objects:
        if obj.type=='MESH' and obj.name.startswith('lod'):obj.name=obj.name.replace('fol_tree_stranger_a','tree_a_canopy_finish')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in bpy.data.objects:
        if obj.type=='MESH' and obj.name.startswith('lod'):obj.hide_set(False);obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,export_apply=True,export_animations=False,export_tangents=True)
    for obj in bpy.data.objects:
        if obj.type=='MESH' and (obj.name.startswith('lod1') or obj.name.startswith('lod2')):
            obj.hide_set(True);obj.hide_render=True
    bpy.ops.wm.save_as_mainfile(filepath=str(path.with_suffix('.blend')))
    report_path=path.parent/'bake_report.json'
    report=json.loads(report_path.read_text());report['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    report_path.write_text(json.dumps(report,indent=2)+'\n')

def distance_segment(x,y,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)

def ground():
    clean()
    # Blender coordinates. Main route has 2.9m clear compacted core.
    routes=[((0,-14),(0,-5)),((0,-5),(-1.8,1.7)),((-.2,-4),(-6,-7)),((0,-3),(9,-8)),((-1.8,1.7),(-1,8)),((0,-3),(10,4))]
    n=36;verts=[];faces=[];colors=[]
    packed=np.array(color('B7A284')[:3]); loose=np.array(color('948B73')[:3]); moss=np.array(color('677B6B')[:3])
    for j in range(n+1):
        y=-16+j*32/n
        for i in range(n+1):
            x=-16+i*32/n
            d=min(distance_segment(x,y,a,b) for a,b in routes)
            disturbance=.16*math.sin(x*1.5+y*.8)+.09*math.sin(y*2.6-x)
            edge=max(0,min(1,(d-1.45+disturbance)/.7))
            green=max(0,min(1,(d-2.12)/1.2))*(.4+.25*math.sin(x*.8)*math.cos(y*.7))
            c=packed*(1-edge)+loose*edge;c=c*(1-green)+moss*green
            # Fine color drift comes from soil composition, not baked lighting.
            c*=1+.04*math.sin(x*.81+y*.73)
            verts.append((x,y,.018));colors.append(tuple(c)+(1,))
    for j in range(n):
        for i in range(n):
            a=j*(n+1)+i;faces.append((a,a+1,a+n+2,a+n+1))
    mat=material('mineral_soil','FFFFFF',.95,grain=.012)
    vc=mat.node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='SoilComposition'
    mat.node_tree.links.new(vc.outputs['Color'],mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
    obj=mesh('continuous_dust_paths',verts,faces,mat)
    attr=obj.data.color_attributes.new(name='SoilComposition',type='FLOAT_COLOR',domain='POINT')
    for dst,c in zip(attr.data,colors):dst.color=c
    bake_asset.contacts=[{'main_path_compacted_width_m':2.9,'surface_height_m':.018,'topology':'single contiguous plane; no coplanar overlays'}]
    bake_asset('env_ground_market_a',[obj],2048,lod=False,samples=8)

def edges():
    clean()
    stone=material('weathered_mineral','93928A',.91,grain=.008)
    leaf=material('dusty_blue_green','6D8D80',.93)
    objects=[]
    # Paired edge clusters, no scatter in the 2.9m clear travel core.
    for cx,cy in [(-2.15,-10),(2.15,-8.6),(-2.3,-7.3),(2.0,-5.8),(-3.6,-3.1),(1.35,-1.9),(-4.5,.4),(1.0,1.0),(4.8,-5.9),(-6.0,-6.1)]:
        for k in range(3):
            x=cx+.19*math.cos(k*2.5);y=cy+.21*math.sin(k*2.5)
            objects.append(lathe('half_buried_stone',[(.06,-.01),(.12,.018),(.14,.055),(.09,.12),(.01,.135)],(x,y,0),stone,7,oval=(1.25,.82),smooth=False))
        for k in range(5):
            a=k*2.4; x=cx+.35*math.cos(a);y=cy+.32*math.sin(a)
            for j in range(3):
                angle=a+j*2.09;dx,dy=.14*math.cos(angle),.14*math.sin(angle)
                objects.append(mesh('folded_ground_leaf',[(x-.028,y,.018),(x+.028,y,.018),(x+dx,y+dy,.28),(x+dx*.3,y+dy*.3,.12)],[(0,1,3),(1,2,3),(2,0,3)],leaf,True))
    bake_asset('fol_ground_tufts_a',objects,1024,lod=False,samples=8)
    clean()
    stone=material('worn_ceramic_threshold','9C9582',.87,grain=.009)
    objects=[]
    # Short worn threshold accents at the stall, leaving the center open.
    for x in [-3.35,-2.95,-.65,-.25]:
        objects.append(slab('worn_threshold',.34,.29,.004,.04,(x,1.48),stone,.012))
    bake_asset('env_plaza_market_a',objects,1024,lod=False,samples=8)

target=sys.argv[sys.argv.index('--')+1] if '--' in sys.argv else 'stall'
{'stall':stall,'food':food,'tree':tree,'ground':ground,'edges':edges}[target]()
