"""Programmatic polygon-density audit of the Quadriflow LOD0 — no vision tool needed.

Answers the user's concern ("structure destroyed, face & hands not smooth") with ground
truth: how many of the ~10800 quads landed in each body region, and the faces-per-area
density. Quadriflow distributes ~uniformly by surface area, so small/complex parts (face,
hands, feet) get starved. This quantifies exactly that.
"""
from pathlib import Path
import json
import bpy
from mathutils import Vector

BLEND = Path("/Users/a86138/Developer/NativeLingo/art/source/characters/npcs/chr_npc_mira/source_locked_v06/retopo/chr_npc_mira_lod0_quadriflow_v01.blend")
OUT = Path("/Users/a86138/Developer/NativeLingo/art/source/characters/npcs/chr_npc_mira/source_locked_v06/retopo/quadriflow_density_report.json")

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
lod = bpy.data.objects["MIRA_lod0_quadriflow"]
mesh = lod.data
mw = lod.matrix_world

def classify(c: Vector) -> str:
    x, y, z = abs(c.x), c.y, c.z
    if z >= 1.46:
        return "head_face"
    if 1.36 <= z < 1.46:
        return "neck"
    # arms/hands sweep wider x at lower z
    if z >= 0.60 and x >= 0.20:
        # hand vs arm: hand is lower + further out
        if z <= 1.02 and x >= 0.30:
            return "hand"
        return "arm_forearm"
    if 0.55 <= z < 1.36 and x < 0.20:
        return "torso"
    if 0.40 <= z < 0.60:
        return "upper_leg"
    if 0.04 <= z < 0.40:
        return "lower_leg"
    if z < 0.04:
        return "foot"
    return "other"

regions: dict[str, dict] = {}
total_area = 0.0
for p in mesh.polygons:
    c = mw @ p.center
    area = p.area
    total_area += area
    r = classify(c)
    d = regions.setdefault(r, {"faces": 0, "area_m2": 0.0})
    d["faces"] += 1
    d["area_m2"] += area

total_faces = len(mesh.polygons)
report = {
    "schema": "quadriflow_density_report.v1",
    "asset_id": "chr_npc_mira",
    "total_faces": total_faces,
    "total_area_m2": round(total_area, 4),
    "regions": {},
}
for r, d in sorted(regions.items(), key=lambda kv: -kv[1]["faces"]):
    faces = d["faces"]
    area = d["area_m2"]
    report["regions"][r] = {
        "faces": faces,
        "pct_of_faces": round(100 * faces / total_faces, 1),
        "area_m2": round(area, 4),
        "pct_of_area": round(100 * area / total_area, 1),
        "faces_per_m2": round(faces / area, 1) if area else 0,
    }

# explicit head vs torso vs hand comparison
def pct(r): return report["regions"].get(r, {}).get("pct_of_faces", 0.0)
report["summary"] = {
    "head_face_pct": pct("head_face"),
    "two_hands_est_pct": 2 * pct("hand") if "hand" in report["regions"] else pct("hand"),
    "torso_pct": pct("torso"),
    "verdict": (
        "face/hands starved: head + 2 hands together < torso face share"
        if (pct("head_face") + 2 * report["regions"].get("hand", {}).get("pct_of_faces", 0)) < pct("torso")
        else "face/hands reasonably represented"
    ),
}
OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("DENSITY_REPORT", json.dumps(report["summary"], ensure_ascii=False))
print("BY_REGION", json.dumps(report["regions"], ensure_ascii=False))
