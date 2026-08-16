"""Add art-bible vertex-color zones to the existing runtime player FBX WITHOUT
re-running the assembly (which is non-idempotent and would re-scale the mesh).

Imports game/assets/characters/chr_player_juvenile.fbx (the HEAD baseline that
renders at correct scale in Godot), assigns per-zone vertex colors from the
skeleton vertex groups (same zones as player_texture_cli.py / assemble vcol),
then re-exports an FBX that preserves the original units. Godot's cel_base.gdshader
reads COLOR_0 as albedo, so the runtime shows the locked turnaround palette.

Run headless:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/characters/chr_player_juvenile/blender/add_vcol_to_fbx.py
"""
import json
import os
from pathlib import Path

import bpy
from mathutils import Vector

PROJECT = Path(__file__).resolve().parents[5]
FBX = PROJECT / "game/assets/characters/chr_player_juvenile.fbx"
OUT = FBX  # overwrite in place (import post re-runs on the game side)

# Art Bible §4.1 palette
def _rgba(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16)/255.0 for i in (0, 2, 4)) + (1.0,)
SKIN = _rgba("D1B898")
CREST_DARK = _rgba("4A456B")
CREST_LIGHT = _rgba("9B76C4")
ARM_MARK = _rgba("9C827D")
BELT = _rgba("856666")
LEG_PURPLE = _rgba("6E576E")
FOOT_STRAP = _rgba("8C7A6E")


def assign_zones(obj: bpy.types.Object) -> None:
    mesh = obj.data
    # dominant vertex group per vertex
    dom = {}
    for v in mesh.vertices:
        best, best_w = "", -1.0
        for vg in v.groups:
            if vg.weight > best_w:
                best_w, best = vg.weight, obj.vertex_groups[vg.group].name
        dom[v.index] = best
    attr = mesh.color_attributes.new(name="Color", domain="POINT", type="FLOAT_COLOR")

    def zone(v, grp):
        z = v.co.z
        if grp == "Head":
            return CREST_DARK if z > 183.0 else (CREST_LIGHT if z > 177.0 else SKIN)
        if grp in ("LeftArm", "RightArm"):
            lo, hi = (78.0, 126.0) if grp == "LeftArm" else (76.0, 122.0)
            t = (z - lo) / (hi - lo) if hi > lo else 0.0
            return ARM_MARK if 0.42 < t < 0.52 else SKIN
        if grp in ("LeftForeArm", "RightForeArm"):
            return SKIN
        if grp == "Hips":
            t = (z - 50.0) / (103.0 - 50.0)
            return BELT if 0.42 < t < 0.55 else SKIN
        if grp in ("LeftUpLeg", "RightUpLeg"):
            return SKIN
        if grp in ("LeftLeg", "RightLeg"):
            t = z / 84.0
            return LEG_PURPLE if t < 0.55 else SKIN
        if grp in ("LeftFoot", "RightFoot"):
            t = z / 50.0
            return FOOT_STRAP if 0.3 < t < 0.5 else SKIN
        return SKIN

    for v in mesh.vertices:
        attr.data[v.index].color = zone(v, dom[v.index])
    print("[vcol] assigned zones on %s (%d verts)" % (obj.name, len(mesh.vertices)))


def main() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(FBX))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("no mesh in FBX")
    for m in meshes:
        assign_zones(m)
        m.name = "lod0__body"  # Godot LOD contract (double-underscore substring)
    # export preserving units: same params as the assembly's FBX export
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        if o.type in ("ARMATURE", "MESH"):
            o.select_set(True)
    bpy.ops.export_scene.fbx(
        filepath=str(OUT),
        use_selection=True,
        object_types={"ARMATURE", "MESH"},
        bake_anim=True,
        bake_anim_use_all_bones=True,
        bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=True,
        bake_anim_force_startend_keying=True,
        bake_anim_simplify_factor=0.0,
        add_leaf_bones=False,
        axis_forward="-Z",
        axis_up="Y",
        apply_unit_scale=False,
        global_scale=1.0,
    )
    print("[vcol] exported %s (%d KB)" % (OUT.name, OUT.stat().st_size // 1024))


if __name__ == "__main__":
    main()
