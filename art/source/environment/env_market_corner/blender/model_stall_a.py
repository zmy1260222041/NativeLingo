"""Hand-model env_market_stall_a — hero food stall for the 「白昼市场角落」 art-test.

Phase 2 deliverable. Modeled in Blender's native Z-up (X right, Y depth, Z up);
front faces +Y so the glTF exporter's Z-up->Y-up conversion lands the model
facing -Z in Godot (art-bible §8.6 "Y-up, -Z forward"). Origin at the base
(lowest point z=0). One GLB carries three named LOD meshes — lod0__stall,
lod1__stall, lod2__stall — that the runtime env_lod.gd groups by the "lod%d__"
name substring (mirrors character_visual.gd:144-170).

Dimensions mirror game/scripts/main.gd:112-126 (_add_market_canopy) and the
locked blockout (blockout_concept_v01.py build_stall). Shape intent from
CONCEPT.md §2/§3: 弯月壳板 canopy (coral_clay), 浇铸陶体 counter (dust_cream +
tide_teal front), 旧合金补片 posts (bark_plum), 纤维绳结 knots (hearth_amber),
种荚 food tokens sit in clay bowls on the shelf. ≤3 material slots (shell /
clay / alloy) per art-bible §5.3 three-material rule; a 2K atlas replaces these
placeholder PBR slots in Phase 3.

Run headless:

  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/environment/env_market_corner/blender/model_stall_a.py

COORDINATE GOTCHAS (Blender 5.2, from runbook §8):
  - Model in Z-up; do NOT use Y-up coords (walls become floors).
  - Do NOT transform_apply(scale) in this pass — 5.2 collapses location on
    apply(scale=True) and sinks geometry to the origin. Geometry is authored at
    world coords directly; object transforms stay clean for export.
"""
import bpy
import os
import math

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
BLEND_PATH = os.path.join(HERE, "blender/model_stall_a.blend")
GLB_PATH = os.path.join(HERE, "export/env_market_stall_a.glb")

# art-bible §2 palette (linear RGBA for Blender)
PAL = {
    "coral_clay":  (0xD8/255, 0x66/255, 0x5B/255, 1.0),
    "dust_cream":  (0xE7/255, 0xD2/255, 0xA3/255, 1.0),
    "tide_teal":   (0x2F/255, 0x8C/255, 0x87/255, 1.0),
    "lichen_mint": (0x78/255, 0xC9/255, 0xA4/255, 1.0),
    "hearth_amber":(0xF2/255, 0xA8/255, 0x5B/255, 1.0),
    "bark_plum":   (0x5A/255, 0x3F/255, 0x58/255, 1.0),
    "silt_ink":    (0x17/255, 0x24/255, 0x3B/255, 1.0),
    "warm_apricot":(0xBF/255, 0xA9/255, 0x82/255, 1.0),
    "bone_white":  (0xF5/255, 0xE9/255, 0xD2/255, 1.0),
}

# 3 material slots (art-bible §5.3: shell / clay / alloy)
SLOT_SHELL = "mat_env_stall_shell"   # canopy, canopy patches
SLOT_CLAY  = "mat_env_stall_clay"    # counter, counter front, shelf bowls
SLOT_ALLOY = "mat_env_stall_alloy"   # posts, bases, caps, shelf, knots, patches


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def slot_material(name):
    """Return the shared per-slot material, colored by its primary semantic."""
    colors = {
        SLOT_SHELL: PAL["coral_clay"],
        SLOT_CLAY: PAL["dust_cream"],
        SLOT_ALLOY: PAL["bark_plum"],
    }
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = colors[name]
    bsdf.inputs["Roughness"].default_value = 0.8
    return mat


def link_mesh(mesh, name, mat, collection):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def set_vertex_color(mesh, color):
    """Fill a corner-domain float color attribute (exports as glTF COLOR_0)."""
    attr = mesh.color_attributes.new(name="Color", domain='CORNER', type='FLOAT_COLOR')
    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            attr.data[loop_idx].color = (color[0], color[1], color[2], 1.0)


def roof_height(x, y):
    """Canopy shell outer-surface height at (x, y) in Blender Z-up.

    The shell rises from the post-cap tops (|x|=1.6 at z=2.76) toward the
    ridge (z=3.30 at x=0), with 弯月 upturned eaves beyond the posts (x>1.6)
    and at both Y ends. Sitting the shell on the posts removes the
    floating-canopy disconnect seen in the first preview.
    """
    POST_X, EDGE_X, RIDGE = 1.6, 2.1, 0.54
    POST_Y, EDGE_Y = 1.15, 1.55
    ax = abs(x)
    if ax <= POST_X:
        arch = RIDGE * (1.0 - (ax / POST_X) ** 2)
    else:
        t = (ax - POST_X) / (EDGE_X - POST_X)  # 0 at post .. 1 at eave edge
        arch = 0.30 * t ** 2
    # 弯月 Y eave starts only beyond the post line so the shell sits ON the
    # posts (z=2.76 at |y|=1.15 matches the cap tops) and curls up at the ends
    ay = abs(y)
    if ay <= POST_Y:
        eave = 0.0
    else:
        t = (ay - POST_Y) / (EDGE_Y - POST_Y)
        eave = 0.16 * t ** 2
    return 2.76 + arch + eave


def roof_sample_axis(seg, lo, hi, critical):
    """Evenly spaced points in [lo, hi] plus the critical interior points
    (post x/y positions) so every LOD's shell sits on the posts identically —
    coarse LOD grids otherwise skip the post line and the canopy floats."""
    pts = {round(lo, 4), round(hi, 4)}
    for c in critical:
        pts.add(round(c, 4))
    for i in range(1, seg + 1):
        pts.add(round(lo + (hi - lo) * i / (seg + 1), 4))
    return sorted(pts)


def build_arc_shell(detail, mat, collection, prefix):
    """Low-arc canopy shell: XZ section follows roof_height, extruded along Y,
    upturned 弯月 eaves at both Y ends, thin-walled with rim. detail = (x_seg, y_seg)."""
    import bmesh
    thickness = 0.06
    x_seg, y_seg = detail
    xs = roof_sample_axis(x_seg, -2.1, 2.1, (-1.6, 0.0, 1.6))
    ys = roof_sample_axis(y_seg, -1.55, 1.55, (-1.15, 0.0, 1.15))
    n_x, n_y = len(xs), len(ys)

    bm = bmesh.new()
    # outer + inner surfaces via a single swept grid (upper shell only, rimed)
    def add_shell(zoff):
        rows = []
        for y in ys:
            rows.append([bm.verts.new((x, y, roof_height(x, y) - zoff)) for x in xs])
        return rows

    outer = add_shell(0.0)
    inner = add_shell(thickness)
    # quads outer surface
    for iy in range(n_y - 1):
        for ix in range(n_x - 1):
            bm.faces.new([outer[iy][ix], outer[iy][ix + 1], outer[iy + 1][ix + 1], outer[iy + 1][ix]])
    # rim: connect outer->inner around the boundary
    for iy in range(n_y - 1):
        bm.faces.new([outer[iy][-1], inner[iy][-1], inner[iy + 1][-1], outer[iy + 1][-1]])
        bm.faces.new([inner[iy][0], outer[iy][0], outer[iy + 1][0], inner[iy + 1][0]])
    for ix in range(n_x - 1):
        bm.faces.new([outer[-1][ix], outer[-1][ix + 1], inner[-1][ix + 1], inner[-1][ix]])
        bm.faces.new([outer[0][ix + 1], outer[0][ix], inner[0][ix], inner[0][ix + 1]])
    # inner faces (visible from below) — flipped so normals point inward
    for iy in range(n_y - 1):
        for ix in range(n_x - 1):
            bm.faces.new([inner[iy][ix], inner[iy + 1][ix], inner[iy + 1][ix + 1], inner[iy][ix + 1]])
    mesh = bpy.data.meshes.new(prefix + "_canopy_mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = link_mesh(mesh, prefix + "_canopy", mat, collection)
    return obj


def build_ribs(detail, mat, collection, prefix):
    """Three 折片/风帆 ribs along Y rising from the shell (direction markers)."""
    import bmesh
    x_positions = (-1.15, 0.0, 1.15)
    hd = 1.55
    for xi in x_positions:
        bm = bmesh.new()
        depth = 2.6
        seg = max(4, detail)
        # rib is a thin flat sail extruded up from the shell
        verts = []
        for iy in range(seg + 1):
            y = -hd + depth * iy / seg
            z0 = roof_height(xi, y) + 0.05
            verts.append((bm.verts.new((xi - 0.02, y, z0)),
                          bm.verts.new((xi + 0.02, y, z0)),
                          bm.verts.new((xi + 0.02, y, z0 + 0.2)),
                          bm.verts.new((xi - 0.02, y, z0 + 0.2))))
        for i in range(seg):
            a0, a1, a2, a3 = verts[i]
            b0, b1, b2, b3 = verts[i + 1]
            bm.faces.new([a0, b0, b1, a1])
            bm.faces.new([a1, b1, b2, a2])
            bm.faces.new([a2, b2, b3, a3])
            bm.faces.new([a3, b3, b0, a0])
        bm.faces.new([verts[0][0], verts[0][1], verts[0][2], verts[0][3]])
        bm.faces.new([verts[-1][0], verts[-1][3], verts[-1][2], verts[-1][1]])
        mesh = bpy.data.meshes.new(prefix + "_rib_mesh")
        bm.to_mesh(mesh)
        bm.free()
        obj = link_mesh(mesh, prefix + "_rib", mat, collection)
        obj.name = f"{prefix}_rib_x{xi}"


def build_posts(detail, mat, collection, prefix):
    """Four tapered alloy posts + bases + caps; 旧合金. detail = cyl segments."""
    import bmesh
    seg = detail
    for x in (-1.6, 1.6):
        for y in (-1.15, 1.15):
            # base plinth
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, radius1=0.08, radius2=0.08, depth=0.12, cap_ends=True, segments=seg)
            mesh = bpy.data.meshes.new(prefix + "_base_mesh")
            bm.to_mesh(mesh)
            bm.free()
            o = link_mesh(mesh, prefix + "_base", mat, collection)
            o.location = (x, y, 0.06)
            # tapered shaft
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, radius1=0.055, radius2=0.035, depth=2.6, cap_ends=True, segments=seg)
            mesh = bpy.data.meshes.new(prefix + "_post_mesh")
            bm.to_mesh(mesh)
            bm.free()
            o = link_mesh(mesh, prefix + "_post", mat, collection)
            o.location = (x, y, 0.12 + 1.3)
            # support bowl under the canopy: wide shallow bowl whose rim tucks
            # into the shell so the canopy visibly rests on the posts
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, radius1=0.16, radius2=0.16, depth=0.09, cap_ends=True, segments=seg)
            mesh = bpy.data.meshes.new(prefix + "_cap_mesh")
            bm.to_mesh(mesh)
            bm.free()
            o = link_mesh(mesh, prefix + "_cap", mat, collection)
            o.location = (x, y, 2.71)


def build_counter(detail, mat_clay, mat_alloy, collection, prefix, with_front=True):
    """浇铸陶体 counter + tide_teal service front (service opening kept clear)."""
    import bmesh
    # main counter block (chamfered)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(3.2, 0.9, 0.22), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0.0, 0.0, 0.92), verts=bm.verts)
    if detail >= 3:
        bmesh.ops.bevel(bm, geom=bm.edges, offset=0.035, segments=1)
    mesh = bpy.data.meshes.new(prefix + "_counter_mesh")
    bm.to_mesh(mesh)
    bm.free()
    link_mesh(mesh, prefix + "_counter", mat_clay, collection)
    # counter top lip (承接面, slightly proud)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(3.3, 0.95, 0.03), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0.0, 0.0, 1.045), verts=bm.verts)
    mesh = bpy.data.meshes.new(prefix + "_liptop_mesh")
    bm.to_mesh(mesh)
    bm.free()
    link_mesh(mesh, prefix + "_liptop", mat_clay, collection)
    if with_front:
        # tide_teal service front: two side panels with a clear service opening
        # in the middle (art-bible §5.3: service opening is the largest negative
        # space, never blocked by decor)
        for side_x, w in ((-1.28, 1.04), (1.28, 1.04)):
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, vec=(w, 0.08, 0.6), verts=bm.verts)
            bmesh.ops.translate(bm, vec=(side_x, 0.46, 0.62), verts=bm.verts)
            mesh = bpy.data.meshes.new(prefix + "_front_mesh")
            bm.to_mesh(mesh)
            bm.free()
            set_vertex_color(mesh, PAL["tide_teal"])
            link_mesh(mesh, prefix + "_front", mat_alloy, collection)


def build_shelf(detail, mat_alloy, mat_clay, collection, prefix):
    """Rear shelf + three clay bowls (food-token seating)."""
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(2.6, 0.5, 0.08), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0.0, -0.5, 1.35), verts=bm.verts)
    mesh = bpy.data.meshes.new(prefix + "_shelf_mesh")
    bm.to_mesh(mesh)
    bm.free()
    link_mesh(mesh, prefix + "_shelf", mat_alloy, collection)
    # three clay bowls
    bowl_seg = max(10, detail * 2)
    for dx in (-0.8, 0.0, 0.8):
        bm = bmesh.new()
        # lathed bowl: stack of ring verts
        rings = []
        prof = [(0.26, 0.0), (0.24, 0.02), (0.16, 0.07), (0.10, 0.09)]
        for j, (rad, dz) in enumerate(prof):
            ring = []
            for k in range(bowl_seg):
                a = math.tau * k / bowl_seg
                ring.append(bm.verts.new((rad * math.cos(a), rad * math.sin(a), dz)))
            rings.append(ring)
        for j in range(len(rings) - 1):
            for k in range(bowl_seg):
                k2 = (k + 1) % bowl_seg
                bm.faces.new([rings[j][k], rings[j][k2], rings[j + 1][k2], rings[j + 1][k]])
        ring_bot = rings[-1]
        bot_center = bm.verts.new((0.0, 0.0, prof[-1][1]))
        for k in range(bowl_seg):
            k2 = (k + 1) % bowl_seg
            bm.faces.new([bot_center, ring_bot[k], ring_bot[k2]])
        mesh = bpy.data.meshes.new(prefix + "_bowl_mesh")
        bm.to_mesh(mesh)
        bm.free()
        o = link_mesh(mesh, prefix + "_bowl", mat_clay, collection)
        o.location = (dx, -0.5, 1.42)
    # two support legs so the shelf reads as mounted, not floating
    for leg_x in (-1.2, 1.2):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, radius1=0.025, radius2=0.025, depth=1.27, cap_ends=True, segments=6)
        mesh = bpy.data.meshes.new(prefix + "_leg_mesh")
        bm.to_mesh(mesh)
        bm.free()
        o = link_mesh(mesh, prefix + "_leg", mat_alloy, collection)
        o.location = (leg_x, -0.5, 0.715)


def build_knots(detail, mat, collection, prefix):
    """纤维绳结 双环扣 at the four post heads (hearth_amber tint in Phase 3)."""
    import bmesh
    seg = max(6, detail)
    for x in (-1.6, 1.6):
        for y in (-1.15, 1.15):
            for ring_i in range(2):
                bm = bmesh.new()
                R, r = 0.075, 0.028
                grid = []
                for i in range(seg):
                    a = math.tau * i / seg
                    ring = []
                    for j in range(4):
                        b = math.tau * j / 4
                        ring.append(bm.verts.new((
                            (R + r * math.cos(b)) * math.cos(a),
                            (R + r * math.cos(b)) * math.sin(a),
                            r * math.sin(b))))
                    grid.append(ring)
                for i in range(seg):
                    i2 = (i + 1) % seg
                    for j in range(4):
                        j2 = (j + 1) % 4
                        bm.faces.new([grid[i][j], grid[i2][j], grid[i2][j2], grid[i][j2]])
                mesh = bpy.data.meshes.new(prefix + "_knot_mesh")
                bm.to_mesh(mesh)
                bm.free()
                o = link_mesh(mesh, prefix + "_knot", mat, collection)
                o.location = (x, y, 2.62)
                o.rotation_euler = (math.radians(55 + ring_i * 70), 0, math.radians(25 + ring_i * 20))


def build_patches(detail, mat_alloy, collection, prefix):
    """生活痕迹: alloy repair patches on posts + a canopy patch. Skip below LOD0."""
    import bmesh
    for (px, py, pz, size) in [(-1.6, -1.15, 1.1, 0.09), (1.6, 1.15, 0.7, 0.08), (-1.6, 1.15, 1.6, 0.07)]:
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, radius1=size / 2, radius2=size / 2, depth=0.012, cap_ends=True, segments=4)
        bm.verts.ensure_lookup_table()
        # make it a flat diamond patch
        mesh = bpy.data.meshes.new(prefix + "_patch_mesh")
        bm.to_mesh(mesh)
        bm.free()
        o = link_mesh(mesh, prefix + "_patch", mat_alloy, collection)
        o.location = (px, py, pz)
        o.rotation_euler.z = math.radians(45)


def build_stall_lod(lod, collection, mats):
    """Assemble one LOD of env_market_stall_a into collection. lod=0,1,2.
    All three LODs share the same three material data blocks (§8.2 ≤3 slots)."""
    prefix = f"lod{lod}__stall"
    if lod == 0:
        arc = (8, 6)
        cyl = 14
        build_arc_shell(arc, mats["shell"], collection, prefix)
        build_ribs(4, mats["shell"], collection, prefix)
        build_posts(cyl, mats["alloy"], collection, prefix)
        build_counter(3, mats["clay"], mats["alloy"], collection, prefix)
        build_shelf(7, mats["alloy"], mats["clay"], collection, prefix)
        build_knots(8, mats["alloy"], collection, prefix)
        build_patches(1, mats["alloy"], collection, prefix)
    elif lod == 1:
        arc = (4, 3)
        cyl = 8
        build_arc_shell(arc, mats["shell"], collection, prefix)
        build_posts(cyl, mats["alloy"], collection, prefix)
        build_counter(2, mats["clay"], mats["alloy"], collection, prefix)
        build_shelf(5, mats["alloy"], mats["clay"], collection, prefix)
        build_knots(6, mats["alloy"], collection, prefix)
    else:
        # LOD2: silhouette only — flat shell, plain posts, plain counter+shelf
        arc = (2, 1)
        cyl = 6
        build_arc_shell(arc, mats["shell"], collection, prefix)
        build_posts(cyl, mats["alloy"], collection, prefix)
        build_counter(0, mats["clay"], mats["alloy"], collection, prefix)
        build_shelf(3, mats["alloy"], mats["clay"], collection, prefix)


def export_glb():
    os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=GLB_PATH,
        export_format='GLB',
        use_selection=False,
        export_yup=True,
        export_apply=True,
        # "ACTIVE" keeps the authored layer as COLOR_0; the default "MATERIAL"
        # prepends a white COLOR_0 that Godot then reads instead.
        export_vertex_color="ACTIVE",
    )
    print(f"MODEL_STALL_EXPORTED {GLB_PATH} ({os.path.getsize(GLB_PATH)/1024:.0f} KB)")


def main():
    reset_scene()
    mats = {
        "shell": slot_material(SLOT_SHELL),
        "clay": slot_material(SLOT_CLAY),
        "alloy": slot_material(SLOT_ALLOY),
    }
    for lod in range(3):
        col = bpy.data.collections.new(f"Stall_LOD{lod}")
        bpy.context.scene.collection.children.link(col)
        build_stall_lod(lod, col, mats)
    export_glb()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print("MODEL_STALL_DONE blend=%s glb=%s" % (BLEND_PATH, GLB_PATH))


if __name__ == "__main__":
    main()
