"""Retarget the user-authored Mixamo actions onto the game's player rig.

The Mixamo source FBXs were authored against a T-pose made from the game's
own LOD0 mesh.  The source and target therefore have the same proportions, but
their bone names, local rolls, and rest pose orientations are not identical.

Three rotation-only retargeting algorithms are evaluated for every action:

``local_delta``
    Copy the source pose-bone rotation basis by name.  This is the cheap
    same-rest-axis assumption used by many simple Mixamo importers.

``world_rest``
    Reconstruct each source bone's world-space orientation, calibrate that
    bone from source rest to target rest, and solve the target local rotation
    needed to produce that orientation.  This is the preferred path when bone
    rolls or the target's A/T-pose differs from Mixamo's rest.

``pose_direction``
    Match every target bone to the source action's posed world-space direction,
    then transfer only the source twist around that bone's own Y axis.  This is
    the safe path when the source Mixamo rig has a T-pose rest but the skinned
    game rig has an arms-down rest pose.  Applying the T-pose delta twice is
    what previously folded the player's hands and feet across the body.

The report compares every mapped bone at every source keyframe against the
source animation's world-space orientation.  The lower mean error wins per
action.  New actions are in-place: cyclic/root drift is removed because
PlayerController moves the CharacterBody3D, while local Hips motion (including
the authored 180-degree body rotation) remains available to the runtime.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
      --factory-startup --python retarget_mixamo_actions.py

Outputs:
    game/assets/characters/chr_player_juvenile_mixamo.fbx
    source_locked_v06/mixamo_retarget_report.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector


PROJECT = Path(__file__).resolve().parents[5]
TARGET_FBX = PROJECT / "game/assets/characters/chr_player_juvenile.fbx"
SOURCE_DIR = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v06/anime"
OUTPUT_FBX = PROJECT / "game/assets/characters/chr_player_juvenile_mixamo.fbx"
REPORT_JSON = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v06/mixamo_retarget_report.json"
RUNTIME_REPORT_JSON = PROJECT / "game/assets/characters/chr_player_juvenile_mixamo_retarget.json"

ALGORITHMS = ("local_delta", "world_rest", "pose_direction")
IDENTITY_Q = Quaternion((1.0, 0.0, 0.0, 0.0))
BONE_Y = Vector((0.0, 1.0, 0.0))

# The source is a standard Mixamo armature.  The target is the 28-bone
# Tencent/legacy Mixamo-named armature inside chr_player_juvenile.fbx.
BONE_MAP = {
    "mixamorig:Hips": "Hips",
    "mixamorig:Spine": "Spine",
    "mixamorig:Spine1": "Spine1",
    "mixamorig:Spine2": "Spine2",
    "mixamorig:Neck": "Neck",
    "mixamorig:Head": "Head",
    "mixamorig:LeftShoulder": "LeftShoulder",
    "mixamorig:LeftArm": "LeftArm",
    "mixamorig:LeftForeArm": "LeftForeArm",
    "mixamorig:LeftHand": "LeftHand",
    "mixamorig:RightShoulder": "RightShoulder",
    "mixamorig:RightArm": "RightArm",
    "mixamorig:RightForeArm": "RightForeArm",
    "mixamorig:RightHand": "RightHand",
    "mixamorig:LeftUpLeg": "LeftUpLeg",
    "mixamorig:LeftLeg": "LeftLeg",
    "mixamorig:LeftFoot": "LeftFoot",
    "mixamorig:LeftToeBase": "LeftToeBase",
    "mixamorig:RightUpLeg": "RightUpLeg",
    "mixamorig:RightLeg": "RightLeg",
    "mixamorig:RightFoot": "RightFoot",
    "mixamorig:RightToeBase": "RightToeBase",
}

ACTION_SPECS = (
    ("Standing Idle.fbx", "anim_chr_player_idle_neutral", True),
    ("Walking.fbx", "anim_chr_player_walk_forward", True),
    ("Standard Run.fbx", "anim_chr_player_run_forward", True),
    ("Pointing Gesture.fbx", "anim_chr_player_gesture_point", False),
    ("Looking Around.fbx", "anim_chr_player_interact_observe", False),
    ("Picking Up.fbx", "anim_chr_player_interact_gather", False),
    ("Walking Turn 180.fbx", "anim_chr_player_turn_180", False),
    ("Jumping.fbx", "anim_chr_player_jump", False),
)

JUMP_CONTACT_BONES = {
    "left": ("mixamorig:LeftFoot", "mixamorig:LeftToeBase"),
    "right": ("mixamorig:RightFoot", "mixamorig:RightToeBase"),
}
# A conservative 2% clearance waits until both feet are visibly clear rather
# than treating a compressed toe/heel key one frame earlier as takeoff.
JUMP_CONTACT_HEIGHT_RATIO = 0.02
JUMP_CONTACT_CONSECUTIVE_FRAMES = 3
ACTION_FPS = 30.0


def _find_new_armature(before: set[bpy.types.Object]) -> bpy.types.Object:
    for obj in bpy.data.objects:
        if obj not in before and obj.type == "ARMATURE":
            return obj
    raise RuntimeError("FBX import did not create an armature")


def _find_armature(name: str | None = None) -> bpy.types.Object:
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE" and (name is None or obj.name == name):
            return obj
    raise RuntimeError(f"armature not found: {name or '<any>'}")


def _import_fbx(path: Path) -> bpy.types.Object:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(path))
    return _find_new_armature(before)


def _active_action(armature: bpy.types.Object) -> bpy.types.Action:
    animation_data = armature.animation_data
    action = animation_data.action if animation_data else None
    if action is not None:
        return action
    raise RuntimeError(f"armature {armature.name} has no active action")


def _bind_action(armature: bpy.types.Object, action: bpy.types.Action) -> None:
    """Bind an action in both Blender 4.x and Blender 5.x layered-action APIs."""
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    slots = getattr(action, "slots", None)
    if slots is not None and len(slots) == 0:
        for id_type in ("OBJECT", "ARMATURE"):
            try:
                slot = slots.new(id_type)
                armature.animation_data.action_slot = slot
                break
            except (TypeError, RuntimeError):
                continue


def _q_from_matrix(matrix: Matrix) -> Quaternion:
    return matrix.to_quaternion().normalized()


def _quaternion_error_degrees(expected: Quaternion, actual: Quaternion) -> float:
    """Return the shortest error; Blender may report q/-q as nearly 360°."""
    degrees = math.degrees(expected.rotation_difference(actual).angle)
    return min(degrees, abs(360.0 - degrees))


def _world_rest_rotations(armature: bpy.types.Object) -> dict[str, Quaternion]:
    object_matrix = armature.matrix_world
    return {
        bone.name: _q_from_matrix(object_matrix @ bone.matrix_local)
        for bone in armature.data.bones
    }


def _world_pose_rotations(armature: bpy.types.Object) -> dict[str, Quaternion]:
    object_q = _q_from_matrix(armature.matrix_world)
    return {
        bone.name: (object_q @ _q_from_matrix(armature.pose.bones[bone.name].matrix)).normalized()
        for bone in armature.data.bones
    }


def _target_rest_local_rotations(
    target: bpy.types.Object,
    target_rest_world: dict[str, Quaternion],
) -> dict[str, Quaternion]:
    object_q = _q_from_matrix(target.matrix_world)
    out: dict[str, Quaternion] = {}
    for bone in target.data.bones:
        parent_q = target_rest_world[bone.parent.name] if bone.parent else object_q
        out[bone.name] = (parent_q.inverted() @ target_rest_world[bone.name]).normalized()
    return out


def _reset_target_pose(target: bpy.types.Object) -> None:
    for pose_bone in target.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.rotation_quaternion = IDENTITY_Q
        # In-place locomotion: keep every bone at its rest translation.
        pose_bone.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()


def _source_to_target_world(
    algorithm: str,
    source_world: dict[str, Quaternion],
    source_basis: dict[str, Quaternion],
    source_rest_world: dict[str, Quaternion],
    target_rest_world: dict[str, Quaternion],
    target_rest_local: dict[str, Quaternion],
    target_object_q: Quaternion,
    target_bones: dict[str, bpy.types.Bone],
) -> dict[str, Quaternion]:
    out: dict[str, Quaternion] = {}
    if algorithm == "local_delta":
        # Apply each source matrix_basis rotation to the corresponding target
        # rest axis, then evaluate the resulting target hierarchy. This is the
        # deliberately naive candidate: it assumes the two rigs share local
        # bone rolls and therefore gives the metric a meaningful baseline.
        ordered = sorted(
            BONE_MAP.items(),
            key=lambda item: sum(1 for _ in _ancestors(target_bones[item[1]])),
        )
        solved = dict(target_rest_world)
        for source_name, target_name in ordered:
            target_bone = target_bones[target_name]
            parent_q = target_object_q if target_bone.parent is None else solved[target_bone.parent.name]
            local_pose_q = target_rest_local[target_name] @ source_basis[source_name]
            out[target_name] = (parent_q @ local_pose_q).normalized()
            solved[target_name] = out[target_name]
        return out
    for source_name, target_name in BONE_MAP.items():
        if algorithm == "world_rest":
            delta = source_rest_world[source_name].inverted() @ source_world[source_name]
            desired = target_rest_world[target_name] @ delta
        elif algorithm == "pose_direction":
            # A Blender bone points along local +Y.  Match that direction to
            # the authored source pose first, independently of the two rigs'
            # very different rest postures.  The residual after the minimal
            # source swing is a twist around local Y; applying it to the
            # target preserves wrist/foot roll without re-applying the
            # Mixamo T-pose-to-action swing to an already arms-down rig.
            source_rest_q = source_rest_world[source_name]
            source_pose_q = source_world[source_name]
            target_rest_q = target_rest_world[target_name]
            source_rest_direction = (source_rest_q @ BONE_Y).normalized()
            source_pose_direction = (source_pose_q @ BONE_Y).normalized()
            target_rest_direction = (target_rest_q @ BONE_Y).normalized()
            source_swing = source_rest_direction.rotation_difference(source_pose_direction)
            source_swing_pose = (source_swing @ source_rest_q).normalized()
            source_twist = (source_swing_pose.inverted() @ source_pose_q).normalized()
            target_swing = target_rest_direction.rotation_difference(source_pose_direction)
            desired = (target_swing @ target_rest_q @ source_twist).normalized()
        else:
            raise ValueError(f"unknown algorithm: {algorithm}")
        out[target_name] = desired.normalized()
    return out


def _apply_target_world_rotations(
    target: bpy.types.Object,
    desired_world: dict[str, Quaternion],
    target_rest_world: dict[str, Quaternion],
    target_rest_local: dict[str, Quaternion],
) -> None:
    """Solve target local pose bases from desired mapped world rotations."""
    object_q = _q_from_matrix(target.matrix_world)
    # Parent-first order is guaranteed by the armature's bone collection order
    # for this rig, but sorting by parent depth makes the assumption explicit.
    mapped = set(desired_world)
    ordered = sorted(
        (target.data.bones[name] for name in mapped),
        key=lambda bone: sum(1 for _ in _ancestors(bone)),
    )
    solved_world = dict(target_rest_world)
    for bone in ordered:
        target_name = bone.name
        desired_q = desired_world[target_name]
        if bone.parent is None:
            parent_pose_q = object_q
        elif bone.parent.name in solved_world:
            parent_pose_q = solved_world[bone.parent.name]
        else:
            parent_pose_q = target_rest_world[bone.parent.name]
        local_pose_q = (parent_pose_q.inverted() @ desired_q).normalized()
        basis_q = (target_rest_local[target_name].inverted() @ local_pose_q).normalized()
        target.pose.bones[target_name].rotation_mode = "QUATERNION"
        target.pose.bones[target_name].rotation_quaternion = basis_q
        solved_world[target_name] = desired_q
    bpy.context.view_layer.update()


def _ancestors(bone: bpy.types.Bone):
    parent = bone.parent
    while parent is not None:
        yield parent
        parent = parent.parent


def _new_action(target: bpy.types.Object, name: str) -> bpy.types.Action:
    action = bpy.data.actions.new(name)
    _bind_action(target, action)
    return action


def _key_target_rotations(target: bpy.types.Object, frame: float, target_names: list[str]) -> None:
    for name in target_names:
        target.pose.bones[name].keyframe_insert(
            data_path="rotation_quaternion",
            frame=frame,
            group=name,
        )


def _key_target_hips_location(target: bpy.types.Object, frame: float) -> None:
    """Key only the in-place Hips offset; CharacterBody3D owns root motion."""
    target.pose.bones["Hips"].keyframe_insert(
        data_path="location",
        frame=frame,
        group="Hips",
    )


def _action_frames(action: bpy.types.Action) -> list[int]:
    start, end = action.frame_range
    return list(range(int(math.ceil(start)), int(math.floor(end)) + 1))


def _source_jump_contact_markers(
    source: bpy.types.Object,
    source_action: bpy.types.Action,
) -> dict[str, float | int | list[dict[str, float | int]]]:
    """Detect authored takeoff/landing from actual source foot clearance.

    A three-frame contact window avoids firing on a single compressed toe
    frame.  The threshold is proportional to the animated character height so
    Mixamo's centimetre FBX import scale cannot change the result.
    """
    _bind_action(source, source_action)
    frames = _action_frames(source_action)
    rows: list[dict[str, float | int]] = []
    all_foot_heights: list[float] = []
    minimum_height = math.inf
    maximum_height = -math.inf
    object_matrix = source.matrix_world

    for frame in frames:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        side_heights: dict[str, float] = {}
        for side, bone_names in JUMP_CONTACT_BONES.items():
            points = [
                object_matrix @ point
                for bone_name in bone_names
                for point in (source.pose.bones[bone_name].head, source.pose.bones[bone_name].tail)
            ]
            side_heights[side] = min(point.z for point in points)
            all_foot_heights.append(side_heights[side])
        for pose_bone in source.pose.bones:
            for point in (object_matrix @ pose_bone.head, object_matrix @ pose_bone.tail):
                minimum_height = min(minimum_height, point.z)
                maximum_height = max(maximum_height, point.z)
        rows.append({
            "frame": frame,
            "left_height": side_heights["left"],
            "right_height": side_heights["right"],
        })

    ground = min(all_foot_heights, default=0.0)
    character_height = max(0.000001, maximum_height - minimum_height)
    threshold = character_height * JUMP_CONTACT_HEIGHT_RATIO
    clearances: list[float] = []
    for row in rows:
        clearance = min(float(row["left_height"]), float(row["right_height"])) - ground
        row["clearance"] = clearance
        clearances.append(clearance)

    window = JUMP_CONTACT_CONSECUTIVE_FRAMES
    takeoff_index = 0
    contact_seen = False
    for index in range(len(clearances) - window + 1):
        contact_seen = contact_seen or clearances[index] <= threshold
        if contact_seen and all(value > threshold for value in clearances[index:index + window]):
            takeoff_index = index
            break

    landing_index = len(frames) - 1
    for index in range(takeoff_index + window, len(clearances) - window + 1):
        if all(value <= threshold for value in clearances[index:index + window]):
            landing_index = index
            break

    first_frame = frames[0]
    return {
        "takeoff_frame": frames[takeoff_index],
        "landing_frame": frames[landing_index],
        "takeoff_time_seconds": round((frames[takeoff_index] - first_frame) / ACTION_FPS, 6),
        "landing_time_seconds": round((frames[landing_index] - first_frame) / ACTION_FPS, 6),
        "source_character_height": round(character_height, 8),
        "contact_threshold": round(threshold, 8),
        "contact_height_ratio": JUMP_CONTACT_HEIGHT_RATIO,
        "consecutive_frames": window,
        "samples": [
            {
                "frame": int(row["frame"]),
                "clearance": round(float(row["clearance"]), 8),
            }
            for row in rows
        ],
    }


def _jump_motion_markers(
    contact_markers: dict,
    frames: list[int],
    selected_hips: list[Vector],
) -> dict:
    takeoff_frame = int(contact_markers["takeoff_frame"])
    landing_frame = int(contact_markers["landing_frame"])
    takeoff_index = frames.index(takeoff_frame)
    landing_index = frames.index(landing_frame)
    takeoff_y = selected_hips[takeoff_index].y
    apex_index = max(
        range(takeoff_index, landing_index + 1),
        key=lambda index: selected_hips[index].y,
    )
    apex_y = selected_hips[apex_index].y
    return {
        **contact_markers,
        "apex_frame": frames[apex_index],
        "apex_time_seconds": round((frames[apex_index] - frames[0]) / ACTION_FPS, 6),
        "hips_takeoff_y_m": round(takeoff_y, 8),
        "hips_apex_y_m": round(apex_y, 8),
        # Only lift after the feet leave the floor contributes to jump height.
        # Crouch-to-stand Hips travel happens while the feet remain planted.
        "authored_airborne_lift_m": round(max(0.0, apex_y - takeoff_y), 8),
        "vertical_axis": "godot_y",
    }


def _pose_fidelity_report(
    source_world: list[dict[str, Quaternion]],
    candidate_world: list[dict[str, Quaternion]],
    source_rest_world: dict[str, Quaternion],
    target_rest_world: dict[str, Quaternion],
    target: bpy.types.Object,
) -> dict[str, float | int | dict[str, float]]:
    """Measure visible pose fidelity, not a retarget formula against itself.

    The old metric used ``target_rest @ source_rest^-1 @ source_pose`` as both
    the algorithm and the expected answer, so ``world_rest`` always scored
    zero even while the limbs visibly folded.  The authored source bone
    direction is now the ground truth.  Full orientation is compared against
    the independent direction-plus-twist construction used by
    ``pose_direction``; endpoint error converts direction error into metres
    using each target bone's real length.
    """
    direction_errors: list[float] = []
    rotation_errors: list[float] = []
    endpoint_errors: list[float] = []
    by_bone: dict[str, list[float]] = {name: [] for name in BONE_MAP.values()}
    world_lengths = {
        name: (target.matrix_world.to_3x3() @ (target.data.bones[name].tail_local - target.data.bones[name].head_local)).length
        for name in BONE_MAP.values()
    }
    for source_frame, candidate_frame in zip(source_world, candidate_world):
        for source_name, target_name in BONE_MAP.items():
            expected = _source_to_target_world(
                "pose_direction",
                source_frame,
                {},
                source_rest_world,
                target_rest_world,
                {},
                IDENTITY_Q,
                {},
            )[target_name]
            actual = candidate_frame[target_name]
            expected_direction = (source_frame[source_name] @ BONE_Y).normalized()
            actual_direction = (actual @ BONE_Y).normalized()
            direction_error = math.degrees(expected_direction.angle(actual_direction))
            rotation_error = _quaternion_error_degrees(expected, actual)
            direction_errors.append(direction_error)
            rotation_errors.append(rotation_error)
            by_bone[target_name].append(direction_error)
            endpoint_errors.append(
                (expected_direction - actual_direction).length * world_lengths[target_name]
            )
    direction_errors.sort()
    rotation_errors.sort()
    endpoint_errors.sort()
    if not direction_errors:
        return {
            "direction_mean_deg": 0.0,
            "direction_p95_deg": 0.0,
            "direction_max_deg": 0.0,
            "rotation_mean_deg": 0.0,
            "endpoint_mean_m": 0.0,
            "endpoint_max_m": 0.0,
            "samples": 0,
            "by_bone_direction_mean_deg": {},
        }
    p95_index = min(len(direction_errors) - 1, int(math.ceil(len(direction_errors) * 0.95)) - 1)
    return {
        "direction_mean_deg": round(sum(direction_errors) / len(direction_errors), 5),
        "direction_p95_deg": round(direction_errors[p95_index], 5),
        "direction_max_deg": round(direction_errors[-1], 5),
        "rotation_mean_deg": round(sum(rotation_errors) / len(rotation_errors), 5),
        "endpoint_mean_m": round(sum(endpoint_errors) / len(endpoint_errors), 6),
        "endpoint_max_m": round(endpoint_errors[-1], 6),
        "samples": len(direction_errors),
        "by_bone_direction_mean_deg": {
            name: round(sum(values) / len(values), 5) if values else 0.0
            for name, values in by_bone.items()
        },
    }


def _position_error_report(
    source_positions: list[Vector],
    candidate_positions: list[Vector],
) -> dict[str, float | bool]:
    """Report fidelity of the retained local Hips motion in metres."""
    errors = [(source - candidate).length for source, candidate in zip(source_positions, candidate_positions)]
    source_span = max(((position - source_positions[0]).length for position in source_positions), default=0.0)
    candidate_span = max(((position - candidate_positions[0]).length for position in candidate_positions), default=0.0)
    drift = (source_positions[-1] - source_positions[0]).length if source_positions else 0.0
    return {
        "mean_m": round(sum(errors) / len(errors), 6) if errors else 0.0,
        "max_m": round(max(errors), 6) if errors else 0.0,
        "source_dynamic_range_m": round(source_span, 6),
        "retarget_dynamic_range_m": round(candidate_span, 6),
        "source_cycle_drift_m": round(drift, 6),
        "has_dynamic_position": source_span > 0.001 and candidate_span > 0.001,
    }


def _retarget_hips_offset(
    source_offset: Vector,
    source_rest_local: dict[str, Quaternion],
    target_rest_local: dict[str, Quaternion],
) -> Vector:
    """Convert a source Hips local offset into the target Hips local axes."""
    axis_delta = target_rest_local["Hips"] @ source_rest_local["mixamorig:Hips"].inverted()
    result = source_offset.copy()
    result.rotate(axis_delta)
    return result


def _sample_candidate(
    source: bpy.types.Object,
    target: bpy.types.Object,
    source_action: bpy.types.Action,
    target_rest_world: dict[str, Quaternion],
    target_rest_local: dict[str, Quaternion],
    source_rest_world: dict[str, Quaternion],
    source_rest_local: dict[str, Quaternion],
    algorithm: str,
    action_name: str,
) -> tuple[
    bpy.types.Action,
    list[dict[str, Quaternion]],
    list[dict[str, Quaternion]],
    list[Vector],
    list[Vector],
    list[int],
]:
    _bind_action(source, source_action)
    frames = _action_frames(source_action)
    action = _new_action(target, action_name)
    source_samples: list[dict[str, Quaternion]] = []
    candidate_samples: list[dict[str, Quaternion]] = []
    source_hips_raw: list[Vector] = []
    candidate_hips: list[Vector] = []
    target_names = list(BONE_MAP.values())

    for frame in frames:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        source_hips_raw.append(source.pose.bones["mixamorig:Hips"].location.copy())

    first_hips = source_hips_raw[0] if source_hips_raw else Vector((0.0, 0.0, 0.0))
    cycle_drift = source_hips_raw[-1] - first_hips if source_hips_raw else Vector((0.0, 0.0, 0.0))

    for frame in frames:
        index = frames.index(frame)
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        source_world = _world_pose_rotations(source)
        source_basis = {
            source_name: _q_from_matrix(source.pose.bones[source_name].matrix_basis)
            for source_name in BONE_MAP
        }
        desired_world = _source_to_target_world(
            algorithm,
            source_world,
            source_basis,
            source_rest_world,
            target_rest_world,
            target_rest_local,
            _q_from_matrix(target.matrix_world),
            {bone.name: bone for bone in target.data.bones},
        )
        _reset_target_pose(target)
        _apply_target_world_rotations(target, desired_world, target_rest_world, target_rest_local)
        phase = index / float(max(1, len(frames) - 1))
        source_offset = source_hips_raw[index] - first_hips - cycle_drift * phase
        target.pose.bones["Hips"].location = _retarget_hips_offset(
            source_offset,
            source_rest_local,
            target_rest_local,
        )
        _key_target_rotations(target, frame, target_names)
        _key_target_hips_location(target, frame)
        source_samples.append(source_world)
        # Sample the pose Blender actually solved, rather than echoing the
        # requested quaternion dictionary back into the metric.
        candidate_samples.append(_world_pose_rotations(target))
        candidate_hips.append(target.pose.bones["Hips"].location.copy())

    action.frame_start = float(frames[0])
    action.frame_end = float(frames[-1])
    source_hips = [
        _retarget_hips_offset(raw - first_hips - cycle_drift * (index / float(max(1, len(frames) - 1))), source_rest_local, target_rest_local)
        for index, raw in enumerate(source_hips_raw)
    ]
    return action, source_samples, candidate_samples, source_hips, candidate_hips, frames


def _remove_objects(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)


def _mount_action(target: bpy.types.Object, action: bpy.types.Action, loop: bool) -> None:
    if loop:
        try:
            action.use_cyclic = True
        except AttributeError:
            pass
    track = target.animation_data.nla_tracks.new()
    track.name = action.name
    start = int(action.frame_range[0])
    strip = track.strips.new(name=action.name, start=start, action=action)
    strip.blend_in = 0.0
    strip.blend_out = 0.0


def _strip_to_runtime_safe_channels(action: bpy.types.Action) -> None:
    """Remove unsafe transforms while retaining dynamic Hips locomotion.

    FBX baking can materialize the armature object's centimeter conversion as
    an object-scale channel. Godot then reads that channel as 100x and the
    whole player grows when the action starts. Locomotion is driven by
    CharacterBody3D, so only the Hips' local, in-place position is allowed.
    """
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                for fcurve in list(channelbag.fcurves):
                    path = fcurve.data_path or ""
                    is_object_transform = path in {
                        "location",
                        "rotation_euler",
                        "rotation_quaternion",
                        "scale",
                    }
                    is_bone_scale = path.startswith('pose.bones["') and path.endswith("].scale")
                    is_non_hips_bone_location = (
                        path.startswith('pose.bones["')
                        and path.endswith("].location")
                        and 'pose.bones["Hips"].location' not in path
                    )
                    if is_object_transform or is_bone_scale or is_non_hips_bone_location:
                        channelbag.fcurves.remove(fcurve)


def _export_target(target: bpy.types.Object) -> None:
    target.animation_data.action = None
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.parent == target:
            obj.select_set(True)
    bpy.context.view_layer.objects.active = target
    OUTPUT_FBX.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.fbx(
        filepath=str(OUTPUT_FBX),
        use_selection=True,
        object_types={"ARMATURE", "MESH"},
        bake_anim=True,
        # Export only keyed pose channels. Baking all bones forces Blender's
        # FBX unit conversion into a root scale track (Godot reads it as 100x).
        bake_anim_use_all_bones=False,
        bake_anim_use_nla_strips=True,
        bake_anim_use_all_actions=False,
        bake_anim_force_startend_keying=True,
        bake_anim_simplify_factor=0.0,
        add_leaf_bones=False,
        axis_forward="-Z",
        axis_up="Y",
        apply_unit_scale=False,
        global_scale=1.0,
    )


def main() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    target = _import_fbx(TARGET_FBX)
    # Keep the target armature name/path from the existing runtime FBX. The
    # procedural greet/offer/clarify actions use Armature/Skeleton3D track
    # paths, so renaming this object would break those legacy gestures.
    target_rest_world = _world_rest_rotations(target)
    target_rest_local = _target_rest_local_rotations(target, target_rest_world)
    # The target FBX's cloud idle is intentionally not carried forward. The
    # user-authored Standing Idle action below replaces it under the same
    # runtime contract name. Clear imported NLA tracks as well so an old idle
    # strip cannot be baked beside the replacement during FBX export.
    target.animation_data.action = None
    for track in list(target.animation_data.nla_tracks):
        target.animation_data.nla_tracks.remove(track)

    report: dict = {
        "target": str(TARGET_FBX.relative_to(PROJECT)),
        "output": str(OUTPUT_FBX.relative_to(PROJECT)),
        "bone_map": BONE_MAP,
        "algorithms": {
            "local_delta": "copy source matrix_basis rotation onto target rest axes",
            "world_rest": "apply each source bone's rest-relative world rotation delta to target rest",
            "pose_direction": "match source posed bone direction and transfer only local-Y twist",
        },
        "actions": {},
    }
    selected_actions: list[tuple[bpy.types.Action, bool]] = []

    for filename, contract_name, loop in ACTION_SPECS:
        source = _import_fbx(SOURCE_DIR / filename)
        source.name = f"Source_{filename.rsplit('.', 1)[0].replace(' ', '_')}"
        source_action = _active_action(source)
        source_rest_world = _world_rest_rotations(source)
        source_rest_local = _target_rest_local_rotations(source, source_rest_world)
        jump_contact_markers = None
        if contract_name == "anim_chr_player_jump":
            jump_contact_markers = _source_jump_contact_markers(source, source_action)

        candidates: dict[str, dict] = {}
        candidate_actions: dict[str, bpy.types.Action] = {}
        candidate_hips_by_algorithm: dict[str, list[Vector]] = {}
        for algorithm in ALGORITHMS:
            action, source_samples, candidate_samples, source_hips, candidate_hips, frames = _sample_candidate(
                source,
                target,
                source_action,
                target_rest_world,
                target_rest_local,
                source_rest_world,
                source_rest_local,
                algorithm,
                f"__candidate_{contract_name}_{algorithm}",
            )
            candidates[algorithm] = {
                "metrics": _pose_fidelity_report(
                    source_samples,
                    candidate_samples,
                    source_rest_world,
                    target_rest_world,
                    target,
                ),
                "hips_position": _position_error_report(source_hips, candidate_hips),
                "frames": [frames[0], frames[-1], len(frames)],
            }
            candidate_actions[algorithm] = action
            candidate_hips_by_algorithm[algorithm] = candidate_hips

        selected_algorithm = min(
            ALGORITHMS,
            key=lambda name: (
                candidates[name]["metrics"]["direction_mean_deg"],
                candidates[name]["metrics"]["rotation_mean_deg"],
            ),
        )
        selected = candidate_actions[selected_algorithm]
        selected.name = contract_name
        _strip_to_runtime_safe_channels(selected)
        selected_actions.append((selected, loop))
        selected_hips = candidate_hips_by_algorithm[selected_algorithm]
        report["actions"][contract_name] = {
            "source": str((SOURCE_DIR / filename).relative_to(PROJECT)),
            "source_action": source_action.name,
            "frames": candidates[selected_algorithm]["frames"],
            "candidates": candidates,
            "selected_algorithm": selected_algorithm,
            "bone_count": len(BONE_MAP),
            "in_place": True,
            "hips_position_keys": [
                {"frame": int(frames[index]), "position": [round(value.x, 8), round(value.y, 8), round(value.z, 8)]}
                for index, value in enumerate(selected_hips)
            ],
        }
        if jump_contact_markers is not None:
            report["actions"][contract_name]["motion_markers"] = _jump_motion_markers(
                jump_contact_markers,
                frames,
                selected_hips,
            )

        # The losing candidate and source armature are no longer needed. Keep
        # the selected action datablock mounted on the target armature.
        for algorithm, action in candidate_actions.items():
            if algorithm != selected_algorithm:
                bpy.data.actions.remove(action)
        _remove_objects([source])

    for action, loop in selected_actions:
        _strip_to_runtime_safe_channels(action)
        _mount_action(target, action, loop)
    _export_target(target)
    report_text = json.dumps(report, ensure_ascii=False, indent=2)
    REPORT_JSON.write_text(report_text, encoding="utf-8")
    RUNTIME_REPORT_JSON.write_text(report_text, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[mixamo-retarget] exported {OUTPUT_FBX}")


if __name__ == "__main__":
    main()
