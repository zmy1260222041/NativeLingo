"""Quadriflow auto-retopology of the Mira Hunyuan high-poly → LOD0 quad candidate.

Block 2 of the retopo flow (design/art/character-modeling-standard.md §2, §4). Quadriflow
consumes the read-only normalized GLB and produces a versioned quad-dominant LOD0
candidate within the key-NPC budget (24–30k tris). No locked baseline is modified; all
outputs land under retopo/.

This pass yields BULK topology only. It deliberately does NOT:
  - place anatomical deformation edge loops (eyes/mouth/jaw, shoulders/elbows/wrists/
    hips/knees/ankles, 3-finger knuckles, split-wedge feet) — that is a manual step;
  - Shrinkwrap-project onto a Gate-A-sculpted high-poly;
  - bake normals / repaint base color / export a runtime glb.
Per §1.5, asset locks were verified before running. The player-side lock drift flagged by
verify_asset_locks.py is unrelated/pre-existing and explicitly deferred.

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python .../source_locked_v06/quadriflow_retopo_v01.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


def project_root() -> Path:
    here = Path(__file__).resolve().parent
    for cand in (here, *here.parents):
        if (cand / "CLAUDE.md").exists() and (cand / "art").is_dir():
            return cand
    raise RuntimeError("could not locate NativeLingo repo root")


PROJECT = project_root()
V06 = Path(__file__).resolve().parent
RETOPO = V06 / "retopo"
VALIDATION = V06 / "validation"
HIPOLY_GLB = V06 / "hunyuan_processed/chr_npc_mira_hunyuan_v06_normalized.glb"
VER = os.environ.get("QUADRIFLOW_VERSION", "v01")
TARGET_FACES = int(os.environ.get("QUADRIFLOW_TARGET", "13000"))  # quad faces (target)
OUT_BLEND = RETOPO / f"chr_npc_mira_lod0_quadriflow_{VER}.blend"
OUT_GLB = RETOPO / f"chr_npc_mira_lod0_quadriflow_{VER}.glb"
REPORT = RETOPO / f"quadriflow_report_{VER}.json"
CLAY = VALIDATION / f"quadriflow_lod0_clay_front_{VER}.png"


def project_relative(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def clean_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "SCN_chr_npc_mira_quadriflow_v01"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"


def import_highpoly() -> bpy.types.Object:
    if not HIPOLY_GLB.exists():
        raise FileNotFoundError(HIPOLY_GLB)
    before = set(bpy.data.objects)
    res = bpy.ops.import_scene.gltf(filepath=str(HIPOLY_GLB))
    if "FINISHED" not in res:
        raise RuntimeError(f"glTF import failed: {res}")
    imported = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not imported:
        raise RuntimeError("no mesh imported")
    bpy.ops.object.select_all(action="DESELECT")
    for o in imported:
        o.select_set(True)
    bpy.context.view_layer.objects.active = imported[0]
    bpy.ops.object.join()
    hipoly = bpy.context.view_layer.objects.active
    hipoly.name = "MIRA_hipoly_ref"
    # Deterministic cleanup: weld coincident verts only (1e-4 m ≈ 0.1 mm → no silhouette change),
    # drop zero-area/length junk, unify normals. Does not alter the immutable on-disk GLB.
    bpy.ops.object.select_all(action="DESELECT")
    hipoly.select_set(True)
    bpy.context.view_layer.objects.active = hipoly
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=1e-4)
    bpy.ops.mesh.dissolve_degenerate()
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    return hipoly


def quadriflow_kwargs() -> dict:
    props = {p.identifier for p in bpy.ops.object.quadriflow_remesh.get_rna_type().properties}
    kw = {"target_faces": TARGET_FACES}
    if "use_preserve_sharp_edges" in props:
        kw["use_preserve_sharp_edges"] = False
    if "use_preserve_boundary" in props:
        kw["use_preserve_boundary"] = False
    return kw


def run_quadriflow(hipoly: bpy.types.Object) -> bpy.types.Object:
    """Duplicate the high-poly; Quadriflow replaces the active object's mesh in place."""
    bpy.ops.object.select_all(action="DESELECT")
    hipoly.select_set(True)
    bpy.context.view_layer.objects.active = hipoly
    bpy.ops.object.duplicate()
    lod = bpy.context.view_layer.objects.active
    lod.name = f"MIRA_lod0_quadriflow_{VER}"
    kw = quadriflow_kwargs()
    print("QUADRIFLOW_KW", kw, flush=True)
    bpy.ops.object.quadriflow_remesh(**kw)
    lod = bpy.context.view_layer.objects.active  # re-fetch (mesh data replaced)
    lod.name = f"MIRA_lod0_quadriflow_{VER}"
    return lod


def analyze(obj: bpy.types.Object) -> dict:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    faces_by_len = {}
    for f in bm.faces:
        faces_by_len[len(f.verts)] = faces_by_len.get(len(f.verts), 0) + 1
    quads = faces_by_len.get(4, 0)
    tris = faces_by_len.get(3, 0)
    ngons = sum(v for k, v in faces_by_len.items() if k > 4)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    loose = sum(1 for v in bm.verts if not v.link_edges)
    valence = {3: 0, 5: 0, "6+": 0}
    boundary_verts = 0
    for v in bm.verts:
        n = len(v.link_edges)
        if v.is_boundary:
            boundary_verts += 1
        if n == 3:
            valence[3] += 1
        elif n == 5:
            valence[5] += 1
        elif n >= 6:
            valence["6+"] += 1
    tri_equiv = tris + 2 * quads + sum(k * v for k, v in faces_by_len.items() if k > 4) - quads  # quads counted
    # tri-equivalent = tris*1 + quads*2 + ngons*(n-2); approximate ngons as (n-2)
    ngon_tri = sum((k - 2) * v for k, v in faces_by_len.items() if k > 4)
    tri_equiv = tris + 2 * quads + ngon_tri
    bm.free()
    return {
        "vertices": len(obj.data.vertices),
        "faces": len(obj.data.polygons),
        "face_breakdown": {"tris": tris, "quads": quads, "ngons": ngons},
        "tri_equivalent": tri_equiv,
        "quad_ratio": round(quads / max(1, quads + tris + ngons), 4),
        "non_manifold_edges": non_manifold,
        "boundary_edges": boundary,
        "boundary_vertices": boundary_verts,
        "loose_vertices": loose,
        "poles": {"valence_3": valence[3], "valence_5": valence[5], "valence_6plus": valence["6+"]},
    }


def bounds(obj: bpy.types.Object) -> dict:
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mn = Vector(tuple(min(p[a] for p in pts) for a in range(3)))
    mx = Vector(tuple(max(p[a] for p in pts) for a in range(3)))
    return {"min": [round(x, 4) for x in mn], "max": [round(x, 4) for x in mx],
            "height_m": round(mx.z - mn.z, 4)}


def render_clay(lod: bpy.types.Object) -> str:
    bpy.ops.object.select_all(action="DESELECT")
    lod.select_set(True)
    bpy.context.view_layer.objects.active = lod
    # isolate lod for the render
    for o in bpy.data.objects:
        if o.type == "MESH" and o is not lod:
            o.hide_render = True
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.film_transparent = False
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "SINGLE"
    sh.single_color = (0.56, 0.54, 0.50)
    sh.show_shadows = True
    sh.show_cavity = True
    sh.cavity_type = "WORLD"
    sh.background_type = "VIEWPORT"
    sh.background_color = (0.055, 0.060, 0.075)
    b = bounds(lod)
    center = Vector(((b["min"][0] + b["max"][0]) / 2, (b["min"][1] + b["max"][1]) / 2, (b["min"][2] + b["max"][2]) / 2))
    h = b["height_m"]
    cam_data = bpy.data.cameras.new("CAM_qf")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = h * 1.14
    cam = bpy.data.objects.new("CAM_qf", cam_data)
    scene.collection.objects.link(cam)
    cam.location = center + Vector((0, -h * 2.6, 0))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.filepath = str(CLAY)
    bpy.ops.render.render(write_still=True)
    # reveal again
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = False
    return str(CLAY)


def export_glb(lod: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    lod.select_set(True)
    bpy.context.view_layer.objects.active = lod
    bpy.ops.export_scene.gltf(
        filepath=str(OUT_GLB), export_format="GLB", use_selection=True,
        export_apply=True, export_materials="PLACEHOLDER", export_animations=False,
    )


def main() -> None:
    RETOPO.mkdir(parents=True, exist_ok=True)
    clean_scene()
    report = {
        "schema": "quadriflow_retopo_v01_report.v1",
        "asset_id": "chr_npc_mira",
        "target_faces": TARGET_FACES,
        "hipoly_source": project_relative(HIPOLY_GLB),
        "notes": [
            "Bulk topology only — no deformation edge loops, no Shrinkwrap, no bake yet.",
            "Quadriflow field-aligned quads; manual loop pass + shrinkwrap to Gate-A high-poly + normal bake are later blocks.",
        ],
        "runtime_export_allowed": False,
    }
    try:
        hipoly = import_highpoly()
        report["hipoly_cleanup"] = {
            "vertices": len(hipoly.data.vertices),
            "faces": len(hipoly.data.polygons),
            "bounds": bounds(hipoly),
        }
        lod = run_quadriflow(hipoly)
        report["lod0"] = {
            "object": lod.name,
            **analyze(lod),
            "bounds": bounds(lod),
        }
        report["quadriflow_kwargs"] = quadriflow_kwargs()
        clay = render_clay(lod)
        export_glb(lod)
        report["outputs"] = {
            "blend": project_relative(OUT_BLEND),
            "glb": project_relative(OUT_GLB),
            "clay_front": project_relative(CLAY),
        }
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND), check_existing=False)
    except Exception as exc:  # noqa: BLE001 - report and exit nonzero
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print("QUADRIFLOW_FAILED", json.dumps(report, ensure_ascii=False), flush=True)
        sys.exit(1)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("QUADRIFLOW_DONE", json.dumps(report, ensure_ascii=False), flush=True)


main()
