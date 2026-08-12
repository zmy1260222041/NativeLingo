"""Procedural idle + walk actions for the player rig (replaces broken cloud walk).

The cloud SubmitAutoRiggingJob walk data arrives corrupted through the FBX layer
(non-mirrored knees, over-bent joints). This module generates symmetric sine-
based idle and walk actions directly on the 28-bone Mixamo-legacy rig.

Bend sign was calibrated empirically: +X rotation on a leg/forearm bone bends
the lower segment BACKWARD (natural knee/elbow flex). All flex uses +X.

Importable: ``from procedural_anims import build_procedural_idle, build_procedural_walk``
Run standalone (renders a verification frame): ``blender -b -P procedural_anims.py``
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

WALK_PERIOD = 24.0   # frames @30fps → 0.8s per cycle (brisk walk)
IDLE_PERIOD = 60.0   # frames @30fps → 2.0s per breath


def _new_action(armature: bpy.types.Object, name: str) -> bpy.types.Action:
    action = bpy.data.actions.new(name)
    if armature.animation_data is None:
        armature.animation_data_create()
    # Blender 5.x layered actions: a freshly-created action has no slot, and
    # keyframe_insert will write fcurves BUT the glTF NLA exporter evaluates the
    # action as empty unless its slot is bound to the armature's animation_data.
    # Create + bind a slot so the exported animation actually carries the data.
    slot = None
    for id_type in ("OBJECT", "ARMATURE"):
        try:
            slot = action.slots.new(id_type)
            break
        except TypeError:
            continue
    armature.animation_data.action = action
    if slot is not None:
        try:
            armature.animation_data.action_slot = slot
        except Exception:
            pass
    return action


def _rot(armature: bpy.types.Object, bone: str, x_deg: float, y_deg: float = 0.0, z_deg: float = 0.0) -> None:
    pb = armature.pose.bones.get(bone)
    if pb is not None:
        pb.rotation_euler = (math.radians(x_deg), math.radians(y_deg), math.radians(z_deg))


def _key_rot(armature: bpy.types.Object, bone: str, frame: int) -> None:
    pb = armature.pose.bones.get(bone)
    if pb is not None:
        pb.keyframe_insert(data_path="rotation_euler", frame=frame)


def build_procedural_idle(armature: bpy.types.Object, name: str = "anim_chr_player_idle_neutral", period: float = IDLE_PERIOD) -> bpy.types.Action:
    action = _new_action(armature, name)
    hips = armature.pose.bones.get("Hips")
    rest_z = hips.location.z if hips else 0.0
    for t in range(0, int(period) + 1):
        ph = 2 * math.pi * t / period
        frame = t + 1
        breath = 2.0 * math.sin(ph)          # deg, spine gentle flex
        bob = 0.012 * math.sin(ph)            # m, hips vertical bob
        sway = 1.5 * math.sin(ph)             # deg, arms subtle
        if hips:
            hips.location.z = rest_z + bob
            hips.keyframe_insert(data_path="location", frame=frame)
        for bn, amp in (("Spine", breath), ("Spine1", breath * 0.7), ("Spine2", breath * 0.5)):
            _rot(armature, bn, amp); _key_rot(armature, bn, frame)
        for bn in ("LeftArm", "RightArm", "LeftForeArm", "RightForeArm"):
            _rot(armature, bn, sway * (0.6 if "ForeArm" in bn else 1.0)); _key_rot(armature, bn, frame)
        _rot(armature, "Head", 0, 0, 0.8 * math.sin(ph)); _key_rot(armature, "Head", frame)
    action.frame_range = (1, period)
    return action


def build_procedural_walk(armature: bpy.types.Object, name: str = "anim_chr_player_walk_forward", period: float = WALK_PERIOD) -> bpy.types.Action:
    action = _new_action(armature, name)
    P = period
    for t in range(0, int(P) + 1):
        ph = 2 * math.pi * t / P
        frame = t + 1
        # legs out of phase by pi; hip swings ±22°, knee flexes 0..55° during swing
        lhip = 22 * math.sin(ph);                         rhip = 22 * math.sin(ph + math.pi)
        lknee = 55 * max(0.0, math.sin(ph + math.pi / 2)); rknee = 55 * max(0.0, math.sin(ph + math.pi + math.pi / 2))
        lankle = -12 * math.sin(ph);                      rankle = -12 * math.sin(ph + math.pi)
        # arms counter-swing; elbow flexes slightly on the forward arm
        larm = -24 * math.sin(ph);                        rarm = -24 * math.sin(ph + math.pi)
        lfa = 10 * max(0.0, math.sin(ph - math.pi / 2));   rfa = 10 * max(0.0, math.sin(ph + math.pi - math.pi / 2))
        sp2y = 6 * math.sin(ph)                            # spine counter-rotation
        for bn, (x, y, z) in {
            "LeftUpLeg": (lhip, 0, 0), "RightUpLeg": (rhip, 0, 0),
            "LeftLeg": (lknee, 0, 0), "RightLeg": (rknee, 0, 0),
            "LeftFoot": (lankle, 0, 0), "RightFoot": (rankle, 0, 0),
            "LeftArm": (larm, 0, 0), "RightArm": (rarm, 0, 0),
            "LeftForeArm": (lfa, 0, 0), "RightForeArm": (rfa, 0, 0),
            "Spine2": (0, sp2y, 0),
        }.items():
            _rot(armature, bn, x, y, z); _key_rot(armature, bn, frame)
    action.frame_range = (1, P)
    return action


def main() -> None:
    """Standalone verification render."""
    FBX = Path(__file__).resolve().parents[1] / "source_locked_v06/cloud_raw/autorig_m26_00.fbx"
    OUT = Path(__file__).resolve().parents[1] / "source_locked_v06/walk_diagnose"
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(FBX))
    armature = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if armature.animation_data:
        armature.animation_data.action = None
        for tr in list(armature.animation_data.nla_tracks):
            armature.animation_data.nla_tracks.remove(tr)

    walk = build_procedural_walk(armature)
    print(f"[proc] built {walk.name} frames {list(walk.frame_range)}")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 500; scene.render.resolution_y = 700
    scene.render.image_settings.file_format = "PNG"
    scene.world = bpy.data.worlds.new("w"); scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.45, 0.47, 0.52, 1.0); bg.inputs[1].default_value = 1.0
    ld = bpy.data.lights.new("key", type="SUN"); ld.energy = 3.0
    lo = bpy.data.objects.new("key", ld); lo.rotation_euler = (0.6, 0.2, 0.4)
    scene.collection.objects.link(lo)

    bpy.context.scene.frame_set(int(WALK_PERIOD // 2))
    bpy.context.view_layer.update()
    cam_data = bpy.data.cameras.new("c"); cam_data.type = "ORTHO"; cam_data.ortho_scale = 2.4
    cam = bpy.data.objects.new("cam", cam_data); cam.location = (5, 0, 1); cam.rotation_euler = (0, math.radians(90), 0)
    scene.collection.objects.link(cam); scene.camera = cam
    scene.render.filepath = str(OUT / "proc_walk_mid.png")
    bpy.ops.render.render(write_still=True)
    print(f"[proc] rendered proc_walk_mid.png")


if __name__ == "__main__":
    main()
