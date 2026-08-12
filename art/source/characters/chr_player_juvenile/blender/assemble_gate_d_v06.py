"""Assemble the Gate-D runtime GLB from the v06 cloud outputs (milestone C1).

Produces ``game/assets/characters/chr_player_juvenile.glb`` containing:
  - the AutoRig 28-bone skeleton (22 deform bones)
  - LOD0 (from AutoRig FBX, already skinned) + LOD1/LOD2 (weight-transferred
    from LOD0 via Blender Data Transfer, then bound to the same armature)
  - idle + walk actions (renamed to the contract animation names, on NLA tracks
    so the glTF exporter emits them as separate animations)
  - one named PrincipledBSDF material in the Art Bible base palette

Gesture animations (greet/offer/clarify) and facial blend shapes are NOT in this
milestone — they need cross-rig retarget / manual authoring and are tracked
separately. The script logs exactly what was emitted so the Gate-D test gaps are
honest.

Run headless:
    /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python art/source/characters/chr_player_juvenile/blender/assemble_gate_d_v06.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

PROJECT = Path(__file__).resolve().parents[5]
CHAR_ROOT = PROJECT / "art/source/characters/chr_player_juvenile"
RAW = CHAR_ROOT / "source_locked_v06/cloud_raw"
OUT_GLB = PROJECT / "game/assets/characters/chr_player_juvenile.glb"
REPORT = CHAR_ROOT / "source_locked_v06/assemble_c1_report.json"

TARGET_HEIGHT_M = 1.78
BASE_COLOR_HEX = "BFA982"  # Art Bible §4.1 warm gray-apricot
IDLE_FBX = RAW / "autorig_m26_00.fbx"
WALK_FBX = RAW / "autorig_m23_00.fbx"
LOD1_GLB = RAW / "reduceface_medium_01.glb"
LOD2_GLB = RAW / "reduceface_low_01.glb"

CONTRACT_IDLE = "anim_chr_player_idle_neutral"
CONTRACT_WALK = "anim_chr_player_walk_forward"
CONTRACT_GREET = "anim_chr_player_gesture_greet"
CONTRACT_OFFER = "anim_chr_player_gesture_offer"
CONTRACT_CLARIFY = "anim_chr_player_gesture_clarify"
MAT_NAME = "mat_chr_player_juvenile"

# Motion-rig (Mixamo-modern, 52 bones w/ fingers) → AutoRig (Mixamo-legacy,
# 28 bones, no fingers) joint mapping. Finger bones have no counterpart and
# are dropped — the hand stays rigid, which is fine for dialogue body gestures.
MOTION_TO_AUTORIG = {
    "Pelvis": "Hips",
    "Spine1": "Spine", "Spine2": "Spine1", "Spine3": "Spine2",
    "Neck": "Neck", "Head": "Head",
    "L_Collar": "LeftShoulder", "L_Shoulder": "LeftArm", "L_Elbow": "LeftForeArm", "L_Wrist": "LeftHand",
    "L_Hip": "LeftUpLeg", "L_Knee": "LeftLeg", "L_Ankle": "LeftFoot", "L_Foot": "LeftToeBase",
    "R_Collar": "RightShoulder", "R_Shoulder": "RightArm", "R_Elbow": "RightForeArm", "R_Wrist": "RightHand",
    "R_Hip": "RightUpLeg", "R_Knee": "RightLeg", "R_Ankle": "RightFoot", "R_Foot": "RightToeBase",
}
GESTURE_JOBS = [
    (RAW / "motion_greet_00.fbx", CONTRACT_GREET),
    (RAW / "motion_offer_00.fbx", CONTRACT_OFFER),
    (RAW / "motion_clarify_00.fbx", CONTRACT_CLARIFY),
]


def project_relative(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_fbx(path: Path) -> None:
    bpy.ops.import_scene.fbx(filepath=str(path))


def import_glb(path: Path) -> None:
    bpy.ops.import_scene.gltf(filepath=str(path))


def find_armature() -> bpy.types.Object:
    for o in bpy.data.objects:
        if o.type == "ARMATURE":
            return o
    raise RuntimeError("no armature in scene")


def collect_actions() -> dict[str, bpy.types.Action]:
    return {a.name: a for a in bpy.data.actions}


# ---------------------------------------------------------------------------
# step 1: import the idle FBX → master armature + LOD0 mesh + idle action
# ---------------------------------------------------------------------------

def step1_import_master() -> tuple[bpy.types.Object, bpy.types.Object, bpy.types.Action]:
    reset_scene()
    before_actions = set(bpy.data.actions.keys())
    import_fbx(IDLE_FBX)
    after_actions = set(bpy.data.actions.keys())
    new_actions = after_actions - before_actions
    armature = find_armature()
    mesh = next(o for o in bpy.data.objects if o.type == "MESH" and o.parent == armature)
    idle_action_name = next(iter(new_actions)) if new_actions else None
    idle_action = bpy.data.actions.get(idle_action_name) if idle_action_name else None
    print(f"[c1] master armature={armature.name} bones={len(armature.data.bones)} mesh={mesh.name} v={len(mesh.data.vertices)} idle_action={idle_action_name}")
    return armature, mesh, idle_action


# ---------------------------------------------------------------------------
# step 2: import the walk FBX, steal its action, remove its objects
# ---------------------------------------------------------------------------

def step2_migrate_walk(master_armature: bpy.types.Object) -> bpy.types.Action | None:
    before = set(a.name for a in bpy.data.actions)
    import_fbx(WALK_FBX)
    after = set(a.name for a in bpy.data.actions)
    new = after - before
    walk_action = bpy.data.actions.get(next(iter(new))) if new else None
    # delete the second armature + mesh; keep only the action data
    for o in list(bpy.data.objects):
        if o.type == "ARMATURE" and o != master_armature:
            bpy.data.objects.remove(o, do_unlink=True)
    # also remove the orphan mesh brought by the walk import
    for o in list(bpy.data.objects):
        if o.type == "MESH" and (o.parent is None or o.parent == master_armature) and o != _master_mesh(master_armature):
            # a second skinned mesh may exist alongside the master; drop it
            if not _is_master_mesh(o):
                bpy.data.objects.remove(o, do_unlink=True)
    print(f"[c1] walk action migrated: {walk_action.name if walk_action else None}")
    return walk_action


def _master_mesh(armature: bpy.types.Object) -> bpy.types.Object | None:
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent == armature]
    return meshes[0] if meshes else None


def _is_master_mesh(obj: bpy.types.Object) -> bool:
    # master = the one whose data has the most vertices (LOD0 from idle import)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        return False
    biggest = max(meshes, key=lambda o: len(o.data.vertices))
    return obj == biggest


# ---------------------------------------------------------------------------
# step 2.5: retarget the three text-to-motion gestures onto the master rig
# ---------------------------------------------------------------------------

def step25_retarget_gestures(master_armature: bpy.types.Object) -> dict[str, bpy.types.Action | None]:
    """Retarget each motion FBX's gesture onto ``master_armature``.

    Uses COPY_ROTATION constraints (world space) baked to a fresh action, so
    Blender's depsgraph resolves the differing bone-local axes between the
    Mixamo-modern motion rig and the Mixamo-legacy auto rig.
    """
    out: dict[str, bpy.types.Action | None] = {}
    for fbx, contract in GESTURE_JOBS:
        if not fbx.exists():
            print(f"[c1] gesture source missing: {fbx.name} → {contract} skipped")
            out[contract] = None
            continue
        action = _retarget_one(master_armature, fbx, contract)
        out[contract] = action
        print(f"[c1] retargeted {fbx.name} → {contract} ({'ok' if action else 'FAILED'})")
    return out


def _retarget_one(master_armature: bpy.types.Object, motion_fbx: Path, contract: str) -> bpy.types.Action | None:
    before_objs = set(o.name for o in bpy.data.objects)
    before_actions = set(a.name for a in bpy.data.actions)
    import_fbx(motion_fbx)
    motion_arm = None
    for o in bpy.data.objects:
        if o.type == "ARMATURE" and o.name not in before_objs:
            motion_arm = o
            break
    if motion_arm is None:
        return None
    new_action_names = set(a.name for a in bpy.data.actions) - before_actions
    motion_action = bpy.data.actions.get(next(iter(new_action_names))) if new_action_names else None
    if motion_action is None:
        return None

    # align the motion armature to the master's world transform so world-space
    # COPY_ROTATION is meaningful
    motion_arm.matrix_world = master_armature.matrix_world.copy()
    bpy.context.view_layer.objects.active = motion_arm
    bpy.ops.object.select_all(action="DESELECT")
    motion_arm.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # drive the motion armature with its action during the bake
    if motion_arm.animation_data is None:
        motion_arm.animation_data_create()
    motion_arm.animation_data.action = motion_action

    # add COPY_ROTATION constraints to each mapped master bone
    bpy.context.view_layer.objects.active = master_armature
    bpy.ops.object.select_all(action="DESELECT")
    master_armature.select_set(True)
    bpy.ops.object.mode_set(mode="POSE")
    for motion_bone, auto_bone in MOTION_TO_AUTORIG.items():
        pb = master_armature.pose.bones.get(auto_bone)
        if pb is None or motion_bone not in motion_arm.data.bones:
            continue
        con = pb.constraints.new(type="COPY_ROTATION")
        con.target = motion_arm
        con.subtarget = motion_bone
        con.target_space = "WORLD"
        con.owner_space = "WORLD"

    frame_start, frame_end = (int(v) for v in motion_action.frame_range)
    bpy.context.scene.frame_start = frame_start
    bpy.context.scene.frame_end = frame_end
    bake_ok = False
    try:
        bpy.ops.nla.bake(
            frame_start=frame_start,
            frame_end=frame_end,
            step=1,
            only_selected=False,
            visual_keying=True,
            clear_constraints=True,
            use_current_action=False,
            clean_curves=False,
            bake_types={"POSE"},
        )
        bake_ok = True
    except Exception as exc:  # noqa: BLE001
        print(f"[c1] bake failed for {contract}: {exc!r}")

    # clear_constraints=True in the bake already removed the constraints;
    # ensure we are back in object mode for the next gesture import.
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    # delete motion arm + its reference meshes
    for o in [motion_arm]:
        bpy.data.objects.remove(o, do_unlink=True)
    # also purge the throwaway body parts the motion FBX brought in
    for o in list(bpy.data.objects):
        if o.name not in before_objs and o.type == "MESH":
            bpy.data.objects.remove(o, do_unlink=True)

    if not bake_ok:
        return None
    baked = master_armature.animation_data.action if master_armature.animation_data else None
    if baked is None:
        return None
    baked.name = contract
    return baked


# ---------------------------------------------------------------------------
# step 3: weight-transfer LOD1/LOD2 from LOD0 and bind to armature
# ---------------------------------------------------------------------------

def step3_add_lod(master_mesh: bpy.types.Object, armature: bpy.types.Object, glb: Path, lod_name: str) -> bpy.types.Object:
    before = set(o.name for o in bpy.data.objects)
    import_glb(glb)
    new_objs = [o for o in bpy.data.objects if o.name not in before]
    lod_mesh = next((o for o in new_objs if o.type == "MESH"), None)
    if lod_mesh is None:
        raise RuntimeError(f"no mesh imported from {glb.name}")

    # detach from the GLB 'world' empty and flatten transforms so vertex
    # positions are in a clean object space we can align to the master.
    lod_mesh.parent = None
    lod_mesh.matrix_world = master_mesh.matrix_world.copy()
    bpy.context.view_layer.objects.active = lod_mesh
    bpy.ops.object.select_all(action="DESELECT")
    lod_mesh.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # manual nearest-vertex weight transfer from master LOD0 (reliable headless)
    _transfer_weights_nearest(master_mesh, lod_mesh)

    # bind to armature
    lod_mesh.parent = armature
    mod = lod_mesh.modifiers.new(name="Armature", type="ARMATURE")
    mod.object = armature
    lod_mesh.name = lod_name
    print(f"[c1] {lod_name}: v={len(lod_mesh.data.vertices)} vg={len(lod_mesh.vertex_groups)} bound to {armature.name}")
    return lod_mesh


def _transfer_weights_nearest(src: bpy.types.Object, dst: bpy.types.Object) -> None:
    """Copy every src vertex group onto dst by nearest-vertex mapping.

    Both objects must already share the same world transform so their object-
    space vertex coordinates are directly comparable.
    """
    src_verts = [v.co for v in src.data.vertices]
    size = len(src_verts)
    kdt = KDTree(size)
    for i, co in enumerate(src_verts):
        kdt.insert(co, i)
    kdt.balance()

    # build src vertex-group weight tables: vg_index → {vertex_index: weight}
    src_vg_names = [g.name for g in src.vertex_groups]
    src_weights: list[dict[int, float]] = [{} for _ in src_vg_names]
    for vg_idx, vg in enumerate(src.vertex_groups):
        for v in src.data.vertices:
            for g in v.groups:
                if g.group == vg_idx and g.weight > 0.0:
                    src_weights[vg_idx][v.index] = g.weight

    # create matching (empty) vertex groups on dst, then fill by nearest source vert
    for vg_idx, name in enumerate(src_vg_names):
        dst.vertex_groups.new(name=name)
    dst_vg_by_idx = [g for g in dst.vertex_groups]

    for dv in dst.data.vertices:
        _co, idx, _dist = kdt.find(dv.co)
        if idx is None:
            continue
        for vg_idx, wmap in enumerate(src_weights):
            w = wmap.get(idx, 0.0)
            if w > 0.0:
                dst_vg_by_idx[vg_idx].add([dv.index], w, "REPLACE")


# ---------------------------------------------------------------------------
# step 4: material + naming + transforms
# ---------------------------------------------------------------------------

def _hex_to_rgba(hex6: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    h = hex6.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, alpha)


def step4_finalize(master_mesh: bpy.types.Object, lods: list[bpy.types.Object], armature: bpy.types.Object) -> None:
    # material
    mat = bpy.data.materials.new(name=MAT_NAME)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = _hex_to_rgba(BASE_COLOR_HEX)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.85
    for m in [master_mesh, *lods]:
        m.data.materials.clear()
        m.data.materials.append(mat)

    # contract mesh names (double-underscore LOD substrings)
    master_mesh.name = "lod0__body"
    for lod, name in zip(lods, ["lod1__body", "lod2__body"]):
        lod.name = name

    # transforms: feet at origin, target height, apply
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.select_all(action="DESELECT")
    for o in [armature, master_mesh, *lods]:
        o.select_set(True)
    # compute combined bbox in world space
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for o in [master_mesh, *lods]:
        for corner in o.bound_box:
            wc = o.matrix_world @ Vector(corner)
            mins.x = min(mins.x, wc.x); mins.y = min(mins.y, wc.y); mins.z = min(mins.z, wc.z)
            maxs.x = max(maxs.x, wc.x); maxs.y = max(maxs.y, wc.y); maxs.z = max(maxs.z, wc.z)
    height = maxs.z - mins.z
    scale = TARGET_HEIGHT_M / height if height > 0 else 1.0
    # apply uniform scale + shift feet (mins.z) to 0
    armature.scale = (scale, scale, scale)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # recompute feet after scale
    mins2 = Vector((1e9, 1e9, 1e9))
    for o in [master_mesh, *lods]:
        for corner in o.bound_box:
            wc = o.matrix_world @ Vector(corner)
            mins2.z = min(mins2.z, wc.z)
    armature.location.z -= mins2.z
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
    print(f"[c1] normalized: height {height:.3f}→{TARGET_HEIGHT_M}m, feet at z=0, scale applied")

    # purge leftover empties (e.g. the GLB 'world' empty)
    for o in list(bpy.data.objects):
        if o.type == "EMPTY":
            bpy.data.objects.remove(o, do_unlink=True)


# ---------------------------------------------------------------------------
# step 5: rename actions + put on NLA tracks so glTF exports multiple anims
# ---------------------------------------------------------------------------

def _set_loop_interpolation(action: bpy.types.Action) -> None:
    # Blender 5.x layered actions do not expose .fcurves directly; best-effort.
    try:
        for fcurve in action.fcurves:
            for kp in fcurve.keyframe_points:
                kp.interpolation = "LINEAR"
    except (AttributeError, ReferenceError):
        pass


def _set_cyclic(action: bpy.types.Action) -> None:
    try:
        action.use_cyclic = True
    except (AttributeError, ReferenceError):
        pass


def step5_actions(armature: bpy.types.Object, idle_action: bpy.types.Action | None, walk_action: bpy.types.Action | None, gestures: dict[str, bpy.types.Action | None]) -> dict[str, str]:
    out: dict[str, str] = {}
    if armature.animation_data is None:
        armature.animation_data_create()

    def _mount(action: bpy.types.Action | None, contract_name: str, loop: bool) -> None:
        if action is None:
            out[contract_name] = "MISSING (no source action)"
            return
        action.name = contract_name
        if loop:
            _set_cyclic(action)
        _set_loop_interpolation(action)
        try:
            track = armature.animation_data.nla_tracks.new()
            track.name = contract_name
            start = int(action.frame_range[0])
            strip = track.strips.new(name=contract_name, start=start, action=action)
            strip.blend_in = 0.0
            strip.blend_out = 0.0
            out[contract_name] = f"mounted frames {int(action.frame_range[0])}-{int(action.frame_range[1])} loop={loop}"
        except Exception as exc:  # noqa: BLE001
            out[contract_name] = f"NLA mount failed: {exc!r}"

    _mount(idle_action, CONTRACT_IDLE, loop=True)
    _mount(walk_action, CONTRACT_WALK, loop=True)
    _mount(gestures.get(CONTRACT_GREET), CONTRACT_GREET, loop=False)
    _mount(gestures.get(CONTRACT_OFFER), CONTRACT_OFFER, loop=False)
    _mount(gestures.get(CONTRACT_CLARIFY), CONTRACT_CLARIFY, loop=False)
    # clear the active action so only NLA-driven animations export
    try:
        armature.animation_data.action = None
    except (AttributeError, ReferenceError):
        pass
    return out


# ---------------------------------------------------------------------------
# step 6: export glTF → GLB
# ---------------------------------------------------------------------------

def step6_export() -> None:
    OUT_GLB.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(OUT_GLB),
        export_format="GLB",
        export_apply=True,
        export_animations=True,
        export_animation_mode="NLA_TRACKS",
        export_skins=True,
        export_morph=False,
        export_yup=True,  # glTF Y-up
        export_extras=False,
        export_cameras=False,
        export_lights=False,
    )
    print(f"[c1] exported → {project_relative(OUT_GLB)} ({OUT_GLB.stat().st_size/1024:.0f} KB)")


def main() -> None:
    report: dict = {"stage": "c1", "outputs": {}}
    armature, master_mesh, idle_action = step1_import_master()
    walk_action = step2_migrate_walk(armature)
    # geometry first, retarget last: the gesture bake must not perturb the
    # armature's world transform while the LOD bbox normalization is measuring it.
    lod1 = step3_add_lod(master_mesh, armature, LOD1_GLB, "lod1__body_tmp")
    lod2 = step3_add_lod(master_mesh, armature, LOD2_GLB, "lod2__body_tmp")
    step4_finalize(master_mesh, [lod1, lod2], armature)
    gestures = step25_retarget_gestures(armature)
    anim_status = step5_actions(armature, idle_action, walk_action, gestures)
    step6_export()

    report["outputs"]["glb"] = project_relative(OUT_GLB)
    report["outputs"]["glb_size_kb"] = round(OUT_GLB.stat().st_size / 1024, 1)
    report["outputs"]["armature_bones"] = len(armature.data.bones)
    report["outputs"]["deform_bones"] = sum(1 for b in armature.data.bones if b.use_deform)
    report["outputs"]["meshes"] = [
        {"name": o.name, "verts": len(o.data.vertices), "faces": len(o.data.polygons), "vertex_groups": len(o.vertex_groups)}
        for o in bpy.data.objects if o.type == "MESH"
    ]
    report["outputs"]["animations"] = anim_status
    report["outputs"]["material"] = MAT_NAME
    report["outputs"]["known_gaps"] = [
        "facial blend shapes blink/jaw/viseme (manual, C3) — Gate D test red until authored",
    ]
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[c1] WROTE report {project_relative(REPORT)}")
    print(json.dumps(report["outputs"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
