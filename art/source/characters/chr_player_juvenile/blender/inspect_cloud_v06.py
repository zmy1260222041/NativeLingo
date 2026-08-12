"""Headless inspection of the v06 cloud outputs (FBX/GLB) to plan the assembly.

Reports, per file: object types, armature bone names + count, mesh vertex/face
counts + material slots, and animation actions. Run:

    /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python art/source/characters/chr_player_juvenile/blender/inspect_cloud_v06.py
"""

from __future__ import annotations

import json
from pathlib import Path

import bpy

PROJECT = Path(__file__).resolve().parents[5]
RAW = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v06/cloud_raw"

FILES = [
    RAW / "autorig_m26_00.fbx",
    RAW / "autorig_m23_00.fbx",
    RAW / "motion_greet_00.fbx",
    RAW / "motion_offer_00.fbx",
    RAW / "motion_clarify_00.fbx",
    RAW / "reduceface_high_01.glb",
    RAW / "reduceface_medium_01.glb",
    RAW / "reduceface_low_01.glb",
]


def _clean() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _describe_armatures() -> list[dict]:
    out = []
    for arm in bpy.data.objects:
        if arm.type != "ARMATURE":
            continue
        bones = [b.name for b in arm.data.bones]
        out.append({"armature": arm.name, "bone_count": len(bones), "bones": bones[:80]})
    return out


def _describe_meshes() -> list[dict]:
    out = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        me = obj.data
        mats = [s.material.name if s.material else None for s in obj.material_slots] if obj.material_slots else []
        vg = [g.name for g in obj.vertex_groups]
        out.append({
            "mesh_object": obj.name,
            "verts": len(me.vertices),
            "faces": len(me.polygons),
            "material_slots": mats,
            "vertex_groups": vg[:40],
            "uv_layers": [uv.name for uv in me.uv_layers],
            "shape_keys": [kb.name for kb in (me.shape_keys.key_blocks if me.shape_keys else [])],
            "has_armature_mod": any(m.type == "ARMATURE" for m in obj.modifiers),
            "parent": obj.parent.name if obj.parent else None,
        })
    return out


def _describe_actions() -> list[dict]:
    out = []
    for act in bpy.data.actions:
        out.append({"action": act.name, "frame_range": list(act.frame_range), "frames": int(act.frame_range[1] - act.frame_range[0])})
    # also NLA tracks / scene frames
    return out


def main() -> None:
    report = {}
    for path in FILES:
        if not path.exists():
            report[path.name] = {"error": "missing"}
            continue
        _clean()
        try:
            if path.suffix.lower() == ".fbx":
                bpy.ops.import_scene.fbx(filepath=str(path))
            elif path.suffix.lower() == ".glb":
                bpy.ops.import_scene.gltf(filepath=str(path))
            else:
                report[path.name] = {"error": f"unknown ext {path.suffix}"}
                continue
        except Exception as exc:  # noqa: BLE001
            report[path.name] = {"error": f"import failed: {exc!r}"}
            continue
        report[path.name] = {
            "objects": [(o.name, o.type) for o in bpy.data.objects],
            "armatures": _describe_armatures(),
            "meshes": _describe_meshes(),
            "actions": _describe_actions(),
            "scene_frame_range": [bpy.context.scene.frame_start, bpy.context.scene.frame_end],
        }
    out_path = RAW.parent / "cloud_outputs_inspect.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {out_path}")
    # brief stdout summary
    for name, info in report.items():
        if "error" in info:
            print(f"\n## {name}: ERROR {info['error']}")
            continue
        arms = info["armatures"]
        meshes = info["meshes"]
        acts = info["actions"]
        print(f"\n## {name}")
        print(f"  objects: {info['objects']}")
        for a in arms:
            print(f"  armature {a['armature']}: {a['bone_count']} bones → {a['bones']}")
        for m in meshes:
            print(f"  mesh {m['mesh_object']}: v={m['verts']} f={m['faces']} mats={m['material_slots']} vg={len(m['vertex_groups'])} uv={m['uv_layers']} shapekeys={m['shape_keys']} armature_mod={m['has_armature_mod']} parent={m['parent']}")
        print(f"  actions: {[(a['action'], a['frames']) for a in acts]}")


if __name__ == "__main__":
    main()
