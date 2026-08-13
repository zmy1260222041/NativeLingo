"""Build a Mixamo-ready T-pose of the runtime player mesh and export it.

Input : game/assets/characters/chr_player_juvenile.fbx (LOD0, A-pose, 22 vgroups)
Output: art/source/characters/chr_player_juvenile/mixamo/
        - chr_player_juvenile_tpose.fbx   (Y-up, +Z forward, 1.7785 m, unrigged)
        - chr_player_juvenile_tpose.obj   (same convention, manual writer)
        - chr_player_juvenile_tpose.blend (working file for manual tweaks)

Why: Mixamo's auto-rigger needs an unrigged single mesh in T-pose. The cloud
outputs are A-pose (arms at the sides, palms facing back), so the arms must be
lifted to horizontal. The cloud FBX's 22 vertex groups (Tencent AutoRiggingJob
weights) drive the pose: every vertex rotates by its combined arm weight, which
is exactly how the game's skinning deforms the mesh — so the deltoid cap opens
with the arm instead of folding like a hinge.

Pose steps per side (Right/Left mirrored):
  1. straighten the elbow — rotate the forearm+hand weight field about the
     elbow until the forearm aligns with the upper arm.
  2. lift the arm — rotate the whole-arm weight field (Arm+ForeArm+Hand+
     Shoulder groups, remapped 0.03->0.28 to full) about the shoulder joint
     until the shoulder->hand_tip direction is horizontal.
  3. palm down — PCA of the hand verts gives the palm thickness axis; twist
     the forearm+hand field about the arm axis until that axis points down.

Then bake to game scale: height = GLB height (1.778538 m), feet at origin,
centered on X and depth. Export FBX (Blender default Y-up mapping, front +Z,
which matches Mixamo's native convention) and an OBJ written manually with the
same convention.

Run headless:  Blender --factory-startup --python make_mixamo_tpose.py
"""
from pathlib import Path

import bpy
import math
from mathutils import Matrix, Quaternion, Vector

PROJECT = Path(__file__).resolve().parents[5]
RUNTIME_FBX = PROJECT / "game/assets/characters/chr_player_juvenile.fbx"
OUT_DIR = PROJECT / "art/source/characters/chr_player_juvenile/mixamo"
GLB_HEIGHT = 1.778538  # reduceface_high_01.glb vertical extent (meters)


def group_verts(mesh_obj, grp, side, thresh=0.5):
    idx = {g.name: g.index for g in mesh_obj.vertex_groups}[side + grp]
    return [v.index for v in mesh_obj.data.vertices
            if any(g.group == idx and g.weight > thresh for g in v.groups)]


def centroid(me, ids):
    c = Vector((0.0, 0.0, 0.0))
    for i in ids:
        c += me.vertices[i].co
    return c / len(ids)


def top_centroid(me, ids, frac):
    srt = sorted(ids, key=lambda i: me.vertices[i].co.z, reverse=True)
    return centroid(me, srt[: max(1, int(len(srt) * frac))])


def bottom_centroid(me, ids, frac):
    srt = sorted(ids, key=lambda i: me.vertices[i].co.z)
    return centroid(me, srt[: max(1, int(len(srt) * frac))])


def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def outer(a, b):
    m = Matrix.Identity(3)
    m.zero()
    for i in range(3):
        for j in range(3):
            m[i][j] = a[i] * b[j]
    return m


def largest_eig(m, iters=80):
    v = Vector((1.0, 0.0, 0.0))
    for _ in range(iters):
        v = (m @ v).normalized()
    return v


def apply_rot_weighted(me, ids_and_w, pivot, q):
    """Rotate vertices about pivot by q with per-vertex weights."""
    for i, w in ids_and_w:
        p = me.vertices[i].co.copy()
        qw = Quaternion().slerp(q, w)
        me.vertices[i].co = pivot + qw @ (p - pivot)


def arm_weight_fields(mesh_obj, side):
    """Combined skin weights per vertex from the auto-rigger's vertex groups.

    The cloud mesh's surface is split into shells (arm separate from torso),
    so topology floods can't cross the shoulder. The auto-rigger's own skin
    weights are the authoritative arm field — cap vertices at the shoulder
    carry partial Arm/Shoulder weights and rotate proportionally, exactly as
    the game's skinning deforms them.
    """
    idx = {g.name: g.index for g in mesh_obj.vertex_groups}
    arm_idx = idx[side + "Arm"]
    fore_idx = idx[side + "ForeArm"]
    hand_idx = idx[side + "Hand"]
    sho_idx = idx.get(side + "Shoulder", -1)
    whole_arm = [0.0] * len(mesh_obj.data.vertices)
    fore_hand = [0.0] * len(mesh_obj.data.vertices)
    for v in mesh_obj.data.vertices:
        for g in v.groups:
            if g.group == arm_idx or g.group == fore_idx or g.group == hand_idx or g.group == sho_idx:
                whole_arm[v.index] += g.weight
            if g.group == fore_idx or g.group == hand_idx:
                fore_hand[v.index] += g.weight
    return whole_arm, fore_hand


def remap_field(field, lo, ramp):
    """0 below lo, smoothstep to 1 over the next `ramp` of weight."""
    return {i: smoothstep((w - lo) / ramp) for i, w in enumerate(field) if w > lo}


def pose_side(me, mesh_obj, side, target):
    arm_ids = sorted(set(group_verts(mesh_obj, "Arm", side))
                     | set(group_verts(mesh_obj, "ForeArm", side))
                     | set(group_verts(mesh_obj, "Hand", side)))
    hand_ids = group_verts(mesh_obj, "Hand", side)
    whole_arm, fore_hand = arm_weight_fields(mesh_obj, side)

    # Joint estimate: start from the top of the upper-arm group, then refine to
    # the center of the adjacent TORSO shell's shoulder cap — the true
    # glenohumeral sits inside the cap, a few units above the arm-group top.
    # A too-low pivot makes the arm leave the body from the side instead of
    # from the shoulder top ("closed" shoulder).
    shoulder0 = top_centroid(me, group_verts(mesh_obj, "Arm", side), 0.15)
    arm_grp_idx = {g.name: g.index for g in mesh_obj.vertex_groups}
    arm_chain = {arm_grp_idx[side + n] for n in ("Arm", "ForeArm", "Hand")}
    cap = [v.index for v in me.vertices
           if not any(g.group in arm_chain and g.weight > 0.3 for g in v.groups)
           and (v.co - shoulder0).length < 6.0
           and v.co.z > shoulder0.z - 2.0]
    shoulder = (sum((me.vertices[i].co for i in cap), Vector((0.0, 0.0, 0.0))) / len(cap)
                if cap else shoulder0)

    elbow = top_centroid(me, group_verts(mesh_obj, "ForeArm", side), 0.2)
    wrist = top_centroid(me, group_verts(mesh_obj, "Hand", side), 0.25)
    hand_tip = bottom_centroid(me, hand_ids, 0.15)

    # 1) straighten elbow: rotate the forearm+hand field about the elbow
    u_dir = (elbow - shoulder).normalized()
    f_dir = (wrist - elbow).normalized()
    if u_dir.angle(f_dir) > 0.07:  # ~4 deg
        fore_w = remap_field(fore_hand, 0.05, 0.30)
        apply_rot_weighted(me, list(fore_w.items()), elbow,
                           f_dir.rotation_difference(u_dir))
        hand_tip = bottom_centroid(me, hand_ids, 0.15)

    # 2) lift to horizontal: rotate the WHOLE arm field about the shoulder
    # joint. The arm and torso are separate surface shells with a natural gap
    # between them in the source A-pose, so only the deltoid cap (torso verts
    # above the joint) needs to follow the arm. Rotating torso verts BELOW the
    # joint bulges the side silhouette into a "flab" under the armpit — the
    # torso side must stay exactly as the source.
    def cap_web_weight(p, s):
        dist = (p - s).length
        return (smoothstep(1.0 - dist / 11.0)
                * smoothstep((p.z - (s.z - 3.0)) / 4.0))

    d = (hand_tip - shoulder).normalized()
    q_lift = d.rotation_difference(target)
    lift_w = remap_field(whole_arm, 0.03, 0.25)
    # Arm-shell verts: taper the rotation near the joint. The shell's ring
    # sits 2.5-7 units from the pivot; rotating it rigidly swings the
    # posterior axilla ring out as a web bridging the arm to the lat. So the
    # BACK side stays anchored out to ~7 units and only reaches full rotation
    # at ~12 (tight posterior axillary fold), while the FRONT keeps the gentler
    # 8-unit taper that the deltoid needs to open.
    for i in lift_w:
        p = me.vertices[i].co
        dist = (p - shoulder).length
        backness = smoothstep((p.y - (shoulder.y + 1.0)) / 5.0)
        w_front = smoothstep(dist / 8.0)
        w_back = smoothstep((dist - 7.0) / 5.0)
        lift_w[i] *= w_front * (1.0 - backness) + w_back * backness
    for i in range(len(me.vertices)):
        if i in lift_w:
            continue
        w_pos = cap_web_weight(me.vertices[i].co, shoulder)
        if w_pos > 0.01:
            lift_w[i] = w_pos
    apply_rot_weighted(me, list(lift_w.items()), shoulder, q_lift)

    # 3) palm down: PCA thickness axis -> (0,0,-1), twisting about the arm axis
    pts = [me.vertices[i].co.copy() for i in hand_ids]
    c = sum(pts, Vector((0.0, 0.0, 0.0))) / len(pts)
    cov = Matrix.Identity(3)
    cov.zero()
    for p in pts:
        e = p - c
        for a in range(3):
            for b in range(3):
                cov[a][b] += e[a] * e[b]
    v0 = largest_eig(cov)
    m2 = cov - (cov @ v0).dot(v0) * outer(v0, v0)
    v1 = largest_eig(m2)
    m3 = m2 - (m2 @ v1).dot(v1) * outer(v1, v1)
    n = largest_eig(m3).normalized()
    n_perp = (n - target * n.dot(target)).normalized()
    q_twist = n_perp.rotation_difference(Vector((0.0, 0.0, -1.0)))
    # The PCA thickness axis has no sign, and aligning it to "down" put the
    # BACK of the hand down (verified by the thumb position: thumb ended on
    # the dorsal side). Flip 180 deg about the arm axis so the palm faces
    # down and the thumb faces the front.
    q_twist = Quaternion(target, math.pi) @ q_twist
    elbow2 = shoulder + q_lift @ (elbow - shoulder)
    twist_w = remap_field(fore_hand, 0.05, 0.30)
    apply_rot_weighted(me, list(twist_w.items()), elbow2, q_twist)
    return len(lift_w)


def bake_to_game_scale(me):
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    xc, yc, zmin, zmax = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs), max(zs)
    s = GLB_HEIGHT / (zmax - zmin)
    for v in me.vertices:
        v.co = Vector(((v.co.x - xc) * s, (v.co.y - yc) * s, (v.co.z - zmin) * s))
    me.update()


def write_obj(me, path):
    """Manual OBJ writer: same convention as the FBX export (x, z, -y)."""
    lines = ["# chr_player_juvenile T-pose LOD0 (reduceface_high), Y-up +Z forward, meters",
             "o chr_player_juvenile_tpose"]
    for v in me.vertices:
        lines.append("v %.6f %.6f %.6f" % (v.co.x, v.co.z, -v.co.y))
    for p in me.polygons:
        lines.append("f " + " ".join(str(vi + 1) for vi in p.vertices))
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(RUNTIME_FBX))
    mesh_obj = next(o for o in bpy.data.objects if o.type == 'MESH')
    me = mesh_obj.data

    n_r = pose_side(me, mesh_obj, "Right", Vector((-1.0, 0.0, 0.0)))
    n_l = pose_side(me, mesh_obj, "Left", Vector((1.0, 0.0, 0.0)))
    print(f"[tpose] lifted verts: R={n_r} L={n_l}")
    me.update()
    bake_to_game_scale(me)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.data.objects.remove(next(o for o in bpy.data.objects if o.type == 'ARMATURE'),
                            do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_obj
    bpy.ops.export_scene.fbx(
        filepath=str(OUT_DIR / "chr_player_juvenile_tpose.fbx"),
        use_selection=True, object_types={'MESH'},
        axis_forward='-Z', axis_up='Y', global_scale=1.0,
        apply_unit_scale=False, apply_scale_options='FBX_SCALE_NONE')
    write_obj(me, OUT_DIR / "chr_player_juvenile_tpose.obj")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_DIR / "chr_player_juvenile_tpose.blend"))
    print(f"[tpose] exported → {OUT_DIR}")


if __name__ == "__main__":
    main()
