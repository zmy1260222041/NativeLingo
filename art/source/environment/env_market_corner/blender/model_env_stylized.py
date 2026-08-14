"""Hand-model the v1.5 stylized assets (art-bible §3.7 A/B, §5.4 斜率混色).

日系开放世界工艺的第一批落地资产：
  - fol_tree_stranger_a   异星树：折面树干 + 多瓣种荚树冠。树冠全部顶点法线从
                          包裹球传递（§3.7.A 球形法线），受光是一个连续圆润
                          体积；2-3 段大色块自顶向下一次明度阶梯；垂挂信号兰
                          种荚点（§2.1 少量异星生态）。
  - env_rock_facet_a      切面岩：凸包大块面 + limited dissolve 合并碎面，
                          flat shading，顶部按坡度烘入暮靛+苔薄荷苔带（§3.7.B）。
  - env_rock_facet_b      宽矮变体。

Same discipline as model_env_settlement.py: Z-up authored, origin at base,
deterministic seeds, export per-collection only, export_vertex_color="ACTIVE".

Run headless:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/environment/env_market_corner/blender/model_env_stylized.py
"""
import bpy
import bmesh
import math
import os
import random as _r
from mathutils import Vector

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
BLEND = os.path.join(HERE, "blender/env_stylized.blend")
EXPORT_DIR = os.path.join(HERE, "export")

PAL = {
    "lichen_mint":  (0x78/255, 0xC9/255, 0xA4/255, 1.0),
    "tide_teal":    (0x2F/255, 0x8C/255, 0x87/255, 1.0),
    "signal_orchid": (0x9A/255, 0x6A/255, 0xCB/255, 1.0),
    "bark_plum":    (0x5A/255, 0x3F/255, 0x58/255, 1.0),
    "dusk_indigo":  (0x34/255, 0x33/255, 0x5E/255, 1.0),
    "basalt":       (0x4B/255, 0x52/255, 0x68/255, 1.0),
    "dust_cream":   (0xE7/255, 0xD2/255, 0xA3/255, 1.0),
}


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mat(name, color, roughness=0.85):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return m


def link_mesh(mesh, name, mat, collection):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    return obj


def scale_color(color, k):
    return (color[0] * k, color[1] * k, color[2] * k, 1.0)


def mix_color(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t, 1.0)


def _smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / max(e1 - e0, 1e-5)))
    return t * t * (3.0 - 2.0 * t)


def fill_vcol_from_verts(mesh, vert_colors):
    """vert_colors: per-vertex rgb tuples -> CORNER 'Color' attribute."""
    attr = mesh.color_attributes.new(name="Color", domain='CORNER', type='FLOAT_COLOR')
    for loop in mesh.loops:
        c = vert_colors[loop.vertex_index]
        attr.data[loop.index].color = (c[0], c[1], c[2], 1.0)


# ================================================================ tree
def _loft_trunk(bm, seg, rings):
    """Faceted tapered trunk with a bend and 3 root flares."""
    zs =    [0.0, 0.55, 1.05, 1.55, 1.92, 2.20]
    bend =  [(0.0, 0.0), (0.05, -0.03), (0.13, 0.02), (0.24, 0.10), (0.35, 0.20), (0.44, 0.28)]
    radii = [0.30, 0.235, 0.185, 0.148, 0.12, 0.10]
    root_angles = [0.4, 2.6, 4.6]
    ring_verts = []
    for i, (z, (bx, by), r) in enumerate(zip(zs, bend, radii)):
        ring = []
        for j in range(seg):
            a = j / seg * math.tau + (0.12 if i % 2 else 0.0)
            rr = r
            if i == 0:  # root flare only on the ground ring
                for ra in root_angles:
                    d = abs(math.atan2(math.sin(a - ra), math.cos(a - ra)))
                    rr += 0.16 * math.exp(-(d * d) / 0.10)
            ring.append(bm.verts.new((bx + math.cos(a) * rr, by + math.sin(a) * rr, z)))
        ring_verts.append(ring)
    for i in range(len(ring_verts) - 1):
        for j in range(seg):
            j2 = (j + 1) % seg
            bm.faces.new((ring_verts[i][j], ring_verts[i][j2],
                          ring_verts[i + 1][j2], ring_verts[i + 1][j]))
    c0 = bm.verts.new((bend[0][0], bend[0][1], -0.03))
    for j in range(seg):
        j2 = (j + 1) % seg
        bm.faces.new((c0, ring_verts[0][j], ring_verts[0][j2]))


def _grow_branch(bm, origin, target, r0, r1, segs=5, rings=5):
    """Loft a tapered limb from inside the trunk toward a canopy lobe."""
    direction = target - origin
    length = direction.length
    if length < 1e-4:
        return
    direction = direction.normalized()
    up = Vector((0.0, 0.0, 1.0))
    if abs(direction.dot(up)) > 0.92:
        up = Vector((1.0, 0.0, 0.0))
    x_axis = direction.cross(up).normalized()
    y_axis = direction.cross(x_axis).normalized()
    ring_verts = []
    for i in range(rings):
        t = i / (rings - 1)
        along = -0.06 + t * (length + 0.06)
        radius = r0 * (1.0 - t) + r1 * t
        center = origin + direction * along
        ring = []
        for j in range(segs):
            a = j / segs * math.tau
            offset = x_axis * math.cos(a) * radius + y_axis * math.sin(a) * radius
            ring.append(bm.verts.new(center + offset))
        ring_verts.append(ring)
    for i in range(rings - 1):
        for j in range(segs):
            j2 = (j + 1) % segs
            bm.faces.new((ring_verts[i][j], ring_verts[i][j2],
                          ring_verts[i + 1][j2], ring_verts[i + 1][j]))
    tip = bm.verts.new(origin + direction * length)
    for j in range(segs):
        j2 = (j + 1) % segs
        bm.faces.new((ring_verts[-1][j], ring_verts[-1][j2], tip))


def build_tree(col, lod):
    """lod0 full lobes, lod1 merged blob canopy, lod2 silhouette."""
    p = f"lod{lod}__tree_a"
    bark = make_mat("mat_tree_bark", PAL["bark_plum"], roughness=0.9)
    leaf = make_mat("mat_tree_leaf", PAL["lichen_mint"], roughness=0.9)

    # ---------------- trunk (flat facets, bark plum)
    seg = 7 if lod == 0 else 5
    bm_t = bmesh.new()
    _loft_trunk(bm_t, seg, 6 if lod == 0 else 5)
    if lod == 0:
        # Trunk centers at the bend rings; limbs start inside the bark and
        # reach the side canopy lobes so they never float off the stem.
        mid = Vector((0.24, 0.10, 1.55))
        high = Vector((0.35, 0.20, 1.92))
        tip = Vector((0.44, 0.28, 2.20))
        for origin, target, r0, r1 in (
            (high, Vector((1.15, -0.10, 2.80)), 0.095, 0.028),
            (high, Vector((-0.20, 0.95, 2.85)), 0.092, 0.026),
            (mid, Vector((-0.45, -0.60, 2.70)), 0.088, 0.024),
            (high, Vector((0.95, 0.75, 2.75)), 0.080, 0.022),
            (tip, Vector((0.44, 0.28, 3.05)), 0.070, 0.030),
        ):
            _grow_branch(bm_t, origin, target, r0, r1)
    bmesh.ops.recalc_face_normals(bm_t, faces=bm_t.faces)
    trunk_mesh = bpy.data.meshes.new(p + "_trunk_mesh")
    bm_t.to_mesh(trunk_mesh)
    bm_t.free()
    link_mesh(trunk_mesh, p + "_trunk", bark, col)
    fill_vcol_from_verts(trunk_mesh, [PAL["bark_plum"][:3]] * len(trunk_mesh.vertices))

    # ---------------- canopy
    canopy_center = Vector((0.44, 0.28, 3.0))
    bm_c = bmesh.new()
    radial_sources = []   # (bmesh vert, radial center)
    lobe_colors = []      # (bmesh vert, hi, lo, z_lo, z_hi)

    def add_lobe(center, radius, hi, lo, seed, u=9, v=7, jitter=0.11):
        rng = _r.Random(seed)
        ret = bmesh.ops.create_uvsphere(bm_c, u_segments=u, v_segments=v, radius=radius)
        verts = ret["verts"]
        bmesh.ops.translate(bm_c, verts=verts, vec=center)
        for vert in verts:
            d = vert.co - center
            if d.length > 1e-4:
                d.normalize()
                vert.co = center + d * (radius * (1.0 + (rng.random() - 0.5) * 2.0 * jitter))
        for vert in verts:
            radial_sources.append((vert, center))
            lobe_colors.append((vert, hi, lo, center.z - radius, center.z + radius))

    mint = PAL["lichen_mint"]
    teal = PAL["tide_teal"]
    if lod == 0:
        add_lobe(Vector((0.44, 0.28, 3.00)), 1.00, scale_color(mint, 0.98),  mix_color(teal, mint, 0.25), seed=11)
        add_lobe(Vector((1.15, -0.10, 2.80)), 0.62, scale_color(mint, 0.92), mix_color(teal, mint, 0.20), seed=12)
        add_lobe(Vector((-0.20, 0.95, 2.85)), 0.66, scale_color(mint, 0.90), mix_color(teal, mint, 0.20), seed=13)
        add_lobe(Vector((-0.45, -0.60, 2.70)), 0.60, mix_color(teal, mint, 0.45), scale_color(teal, 0.95), seed=14)
        add_lobe(Vector((0.95, 0.75, 2.75)), 0.58, scale_color(mint, 0.88), mix_color(teal, mint, 0.25), seed=15)
        add_lobe(Vector((0.38, 0.24, 3.85)), 0.55, scale_color(mint, 1.10), mix_color(teal, mint, 0.35), seed=16)
        add_lobe(Vector((0.10, -0.95, 2.42)), 0.46, scale_color(teal, 1.02), scale_color(teal, 0.80), seed=17)  # hanging skirt
    else:
        add_lobe(Vector((0.44, 0.28, 3.05)), 1.42 if lod == 1 else 1.30,
                 scale_color(mint, 0.98), mix_color(teal, mint, 0.30), seed=21,
                 u=8 if lod == 1 else 6, v=6 if lod == 1 else 5, jitter=0.09)

    # hanging seed pods (信号兰 异星生态 accent, §2.1)
    pod_sets = []
    if lod == 0:
        for pc in [Vector((0.15, -1.05, 2.15)), Vector((-0.55, -0.80, 2.30))]:
            ret = bmesh.ops.create_uvsphere(bm_c, u_segments=7, v_segments=6, radius=0.13)
            verts = ret["verts"]
            bmesh.ops.translate(bm_c, verts=verts, vec=pc)
            orchid = PAL["signal_orchid"]
            for vert in verts:
                radial_sources.append((vert, pc))
                lobe_colors.append((vert, scale_color(orchid, 0.8), orchid,
                                    pc.z - 0.13, pc.z + 0.13))
            pod_sets.append((verts, pc))

    bmesh.ops.recalc_face_normals(bm_c, faces=bm_c.faces)
    bm_c.verts.index_update()
    bm_c.faces.index_update()

    # materialize per-vertex data while the bmesh is alive (index_update makes
    # bmesh indices match the to_mesh() vertex order)
    vert_normals = [Vector((0, 0, 1))] * len(bm_c.verts)
    vert_colors = [(0.4, 0.5, 0.4)] * len(bm_c.verts)
    for vert, center in radial_sources:
        n = Vector((vert.co.x - center.x, vert.co.y - center.y, vert.co.z - center.z + 0.20))
        vert_normals[vert.index] = n.normalized() if n.length > 1e-4 else Vector((0, 0, 1))
    for vert, hi, lo, z_lo, z_hi in lobe_colors:
        vert_colors[vert.index] = mix_color(lo, hi, _smoothstep(z_lo, z_hi, vert.co.z))[:3]

    canopy_mesh = bpy.data.meshes.new(p + "_canopy_mesh")
    bm_c.to_mesh(canopy_mesh)
    bm_c.free()

    # §3.7.A spherical normal transfer: every canopy vertex points radially away
    # from the canopy volume (+up bias so the terminator is one stable arc).
    canopy_mesh.normals_split_custom_set_from_vertices(vert_normals)
    canopy_mesh.update()
    link_mesh(canopy_mesh, p + "_canopy", leaf, col)
    fill_vcol_from_verts(canopy_mesh, vert_colors)


# ================================================================ rocks
def build_rock(col, name, seed, radii, dissolve_deg=14.0, points=44):
    """Convex-hull faceted rock: big planes from limited dissolve, flat shading,
    slope-baked moss top (§3.7.B + §5.4 斜率混色)."""
    side_base = mix_color(PAL["basalt"], PAL["dusk_indigo"], 0.30)
    moss_top = mix_color(scale_color(PAL["lichen_mint"], 0.98), PAL["dusk_indigo"], 0.10)
    mat = make_mat("mat_rock_" + name, PAL["basalt"], 0.9)

    for lod, (pt_count, dissolve, jitter) in enumerate([(points, dissolve_deg, 0.48), (26, 90.0, 0.42)]):
        p = f"lod{lod}__{name}"
        rng = _r.Random(seed + 900 * lod)
        bm = bmesh.new()
        pts = []
        for _ in range(pt_count):
            d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.5, 1.0)))
            if d.length < 1e-3:
                d = Vector((0, 0, 1))
            d.normalize()
            # side-ridge bias: some points push outward horizontally so the
            # profile gains ledges instead of reading as a rounded boulder
            horizontal = 1.0 + (0.30 if rng.random() < 0.30 else 0.0)
            k = 1.0 + (rng.random() - 0.5) * 2.0 * jitter
            pts.append(bm.verts.new(Vector((d.x * radii[0] * horizontal * k,
                                            d.y * radii[1] * horizontal * k,
                                            d.z * radii[2] * k))))
        bmesh.ops.convex_hull(bm, input=pts)
        interior = [v for v in bm.verts if not v.link_faces]
        if interior:
            bmesh.ops.delete(bm, geom=interior, context='VERTS')
        if dissolve < 90.0:
            bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(dissolve),
                                     verts=bm.verts, edges=bm.edges)
            bmesh.ops.dissolve_degenerate(bm, dist=1e-4, edges=bm.edges)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        # ground the mass: sink the lowest point so the base reads buried
        min_z = min(v.co.z for v in bm.verts)
        bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, 0, -min_z - 0.05)))
        mesh = bpy.data.meshes.new(p + "_mesh")
        bm.to_mesh(mesh)
        bm.free()
        link_mesh(mesh, p, mat, col)

        # per-face vcol: slope moss mix + quantized side banding + contact band
        bands = [0.90, 1.0, 1.08]
        rng2 = _r.Random(seed + 500)
        height = max(v.co.z for v in mesh.vertices)
        attr = mesh.color_attributes.new(name="Color", domain='CORNER', type='FLOAT_COLOR')
        for fi, face in enumerate(mesh.polygons):
            nz = face.normal.z
            moss_t = _smoothstep(0.28, 0.62, nz) * _smoothstep(0.14, 0.40, face.center.z / max(height, 1e-3))
            c = mix_color(side_base, moss_top, moss_t)
            c = scale_color(c, bands[int(rng2.random() * 3) % 3])
            if face.center.z < 0.10:
                c = scale_color(c, 0.78)  # contact band (§8.8-2 grounding)
            for loop_idx in face.loop_indices:
                attr.data[loop_idx].color = c


# ================================================================ distant ridge
def _valley_z(x, _y):
    """U-shaped valley: flat corridor, rise only toward the left/right ranges."""
    return 0.02 + 2.2 * _smoothstep(13.0, 34.0, abs(x))


def _add_valley_floor(col, mat):
    """Visual floor under the ranges and out the open valley mouths.
    Leaves the 28 m market square to env_ground_market_a to avoid z-fight."""
    dust = PAL["dust_cream"]
    dusk = PAL["dusk_indigo"]
    x0, x1, y0, y1 = -52.0, 52.0, -40.0, 40.0
    nx, ny = 30, 24
    hole = 13.4
    bm = bmesh.new()
    grid = []
    for iy in range(ny + 1):
        y = y0 + (y1 - y0) * (iy / ny)
        row = []
        for ix in range(nx + 1):
            x = x0 + (x1 - x0) * (ix / nx)
            row.append(bm.verts.new((x, y, _valley_z(x, y))))
        grid.append(row)
    for iy in range(ny):
        for ix in range(nx):
            v00, v10 = grid[iy][ix], grid[iy][ix + 1]
            v01, v11 = grid[iy + 1][ix], grid[iy + 1][ix + 1]
            cx = 0.25 * (v00.co.x + v10.co.x + v01.co.x + v11.co.x)
            cy = 0.25 * (v00.co.y + v10.co.y + v01.co.y + v11.co.y)
            if abs(cx) < hole and abs(cy) < hole:
                continue
            bm.faces.new((v00, v10, v11, v01))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new("valley_floor_mesh")
    bm.to_mesh(mesh)
    bm.free()
    link_mesh(mesh, "valley_floor", mat, col)
    attr = mesh.color_attributes.new(name="Color", domain="CORNER", type="FLOAT_COLOR")
    for face in mesh.polygons:
        t = _smoothstep(12.0, 32.0, abs(face.center.x))
        c = mix_color(dust, dusk, t * 0.72)
        for loop_idx in face.loop_indices:
            attr.data[loop_idx].color = c


def _add_foothill(col, mat, side, rng):
    """Faceted bank from the market edge up into the range, so peaks sit on terrain."""
    dust = PAL["dust_cream"]
    dusk = PAL["dusk_indigo"]
    x_inner, x_outer = 13.5 * side, 40.0 * side
    y0, y1 = -28.0, 28.0
    nx, ny = 6, 10
    bm = bmesh.new()
    grid = []
    for iy in range(ny + 1):
        y = y0 + (y1 - y0) * (iy / ny)
        row = []
        for ix in range(nx + 1):
            t = ix / nx
            x = x_inner + (x_outer - x_inner) * t
            z = 0.04 + (t * t) * (2.6 + rng.uniform(-0.25, 0.40)) + rng.uniform(-0.10, 0.10)
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    for iy in range(ny):
        for ix in range(nx):
            bm.faces.new((grid[iy][ix], grid[iy][ix + 1],
                          grid[iy + 1][ix + 1], grid[iy + 1][ix]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    name = "valley_foothill_l" if side < 0 else "valley_foothill_r"
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    link_mesh(mesh, name, mat, col)
    attr = mesh.color_attributes.new(name="Color", domain="CORNER", type="FLOAT_COLOR")
    for face in mesh.polygons:
        t = _smoothstep(14.0, 34.0, abs(face.center.x))
        c = mix_color(dust, dusk, 0.35 + 0.55 * t)
        for loop_idx in face.loop_indices:
            attr.data[loop_idx].color = c


def _add_valley_peak(col, mat, side, along, height, half_y, half_x, rng, index):
    """One planted faceted peak. `side` is -1 (left/-X) or +1 (right/+X)."""
    side_base = scale_color(PAL["dusk_indigo"], 0.92)
    top_tint = mix_color(PAL["dusk_indigo"], PAL["basalt"], 0.45)
    cx = side * (18.8 + half_x * 0.88)
    cy = along
    bm = bmesh.new()
    pts = []
    for _ in range(28):
        d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.15, 1.0)))
        if d.length < 1e-3:
            d = Vector((0, 0, 1))
        d.normalize()
        k = 1.0 + (rng.random() - 0.5) * 0.24
        pts.append(bm.verts.new(Vector((d.x * half_x, d.y * half_y, d.z * height)) * k))
    # Wide sole so the hull sits on the valley floor instead of tapering to a point.
    for i in range(10):
        a = i / 10 * math.tau
        pts.append(bm.verts.new((
            math.cos(a) * half_x * 0.92,
            math.sin(a) * half_y * 0.92,
            rng.uniform(0.0, 0.45),
        )))
    bmesh.ops.convex_hull(bm, input=pts)
    interior = [v for v in bm.verts if not v.link_faces]
    if interior:
        bmesh.ops.delete(bm, geom=interior, context="VERTS")
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(16), verts=bm.verts, edges=bm.edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    min_z = min(v.co.z for v in bm.verts)
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((cx, cy, -min_z - 1.8)))
    inner = min(v.co.x * side for v in bm.verts)
    if inner < 18.2:
        bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((side * (18.2 - inner), 0.0, 0.0)))
    mesh = bpy.data.meshes.new(f"ridge_peak_{index}_mesh")
    bm.to_mesh(mesh)
    bm.free()
    link_mesh(mesh, f"ridge_peak_{index}", mat, col)
    h_max = max(v.co.z for v in mesh.vertices)
    attr = mesh.color_attributes.new(name="Color", domain="CORNER", type="FLOAT_COLOR")
    for face in mesh.polygons:
        t = _smoothstep(-1.8, h_max, face.center.z)
        c = mix_color(side_base, top_tint, 0.22 + 0.58 * t)
        for loop_idx in face.loop_indices:
            attr.data[loop_idx].color = c


def build_ridge(col):
    """Valley: tall ranges only on left/right (±X), open north/south mouths,
    and a floor that runs under the peaks so the settlement is not ringed in."""
    mat = make_mat("mat_ridge", PAL["dusk_indigo"], 0.95)
    rng = _r.Random(97)
    _add_valley_floor(col, mat)
    _add_foothill(col, mat, -1, rng)
    _add_foothill(col, mat, 1, rng)
    # (along Y, height, half-span along valley, half-span toward/away from corridor)
    layout = [
        (-20.0, 16.0, 6.4, 9.0),
        (-12.0, 25.0, 7.4, 11.0),
        (-3.5, 34.0, 8.0, 12.5),
        (6.0, 36.0, 7.8, 12.0),
        (14.5, 26.0, 7.2, 11.0),
        (22.0, 15.5, 6.2, 9.0),
    ]
    index = 0
    for side in (-1, 1):
        for along, height, half_y, half_x in layout:
            along = along + rng.uniform(-0.8, 0.8)
            height = height + rng.uniform(-1.4, 1.8)
            _add_valley_peak(col, mat, side, along, height, half_y, half_x, rng, index)
            index += 1


def export_glb(name):
    out = os.path.join(EXPORT_DIR, name + ".glb")
    bpy.ops.object.select_all(action="DESELECT")
    col = bpy.data.collections[name]
    for obj in col.objects:
        obj.select_set(True)
    # export_vertex_color="ACTIVE": the default ("MATERIAL") emits a phantom white
    # COLOR_0 ahead of the authored layer, and Godot's COLOR builtin only reads
    # COLOR_0 — so every hand-authored per-part tint was silently dropped.
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True,
                              export_yup=True, export_apply=True,
                              export_vertex_color="ACTIVE")
    print(f"STYLIZED_EXPORT {name} ({os.path.getsize(out)/1024:.0f} KB)")


def main():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    reset_scene()
    builders = {
        "fol_tree_stranger_a": lambda col: [build_tree(col, lod) for lod in (0, 1, 2)],
        "env_rock_facet_a": lambda col: build_rock(col, "rock_a", seed=31, radii=(0.72, 0.58, 1.12)),
        "env_rock_facet_b": lambda col: build_rock(col, "rock_b", seed=57, radii=(1.40, 1.00, 0.66), dissolve_deg=12.0, points=52),
        "env_ridge_distant_a": build_ridge,
    }
    for name, build in builders.items():
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
        build(col)
        export_glb(name)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print("ENV_STYLIZED_DONE blend=%s" % BLEND)


if __name__ == "__main__":
    main()
