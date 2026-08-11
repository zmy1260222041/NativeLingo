"""Deterministically import, normalize, render, save, and export a Rodin NPC base."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Vector


PROJECT = Path(__file__).resolve().parents[5]


def project_relative(path: Path | str) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-root", required=True, type=Path)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--target-height", required=True, type=float)
    return parser.parse_args(argv)


def clean_scene(asset_id: str) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = f"SCN_{asset_id}_rodin_base"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"


def input_glb(asset_root: Path) -> Path:
    canonical = asset_root / "rodin_raw/base_basic_pbr.glb"
    if canonical.exists():
        return canonical
    candidates = sorted((asset_root / "rodin_raw").glob("*.glb"))
    if not candidates:
        raise FileNotFoundError(f"No Rodin GLB in {asset_root / 'rodin_raw'}")
    return candidates[0]


def import_model(path: Path, asset_id: str) -> list[bpy.types.Object]:
    before = set(bpy.data.objects)
    result = bpy.ops.import_scene.gltf(filepath=str(path))
    if "FINISHED" not in result:
        raise RuntimeError(f"Rodin GLB import failed: {result}")
    objects = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if not objects:
        raise RuntimeError("Rodin GLB imported without mesh objects")
    for index, obj in enumerate(objects):
        obj.name = f"RODIN_{asset_id}_base_{index:02d}"
        obj.hide_render = False
        obj.hide_viewport = False
        obj.hide_set(False)
        obj.display_type = "TEXTURED"
    return objects


def topology(objects: list[bpy.types.Object]) -> dict[str, int]:
    totals = {"vertices": 0, "faces": 0, "triangles": 0, "non_manifold_edges": 0, "loose_vertices": 0}
    for obj in objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        totals["vertices"] += len(bm.verts)
        totals["faces"] += len(bm.faces)
        totals["triangles"] += sum(max(1, len(face.verts) - 2) for face in bm.faces)
        totals["non_manifold_edges"] += sum(1 for edge in bm.edges if not edge.is_manifold)
        totals["loose_vertices"] += sum(1 for vertex in bm.verts if not vertex.link_edges)
        bm.free()
    return totals


def weld(objects: list[bpy.types.Object]) -> dict[str, int]:
    before = sum(len(obj.data.vertices) for obj in objects)
    for obj in objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.000001)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update(calc_edges=True)
        for face in obj.data.polygons:
            face.use_smooth = True
    report = topology(objects)
    report["vertices_before_weld"] = before
    return report


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    return (
        Vector(tuple(min(point[axis] for point in points) for axis in range(3))),
        Vector(tuple(max(point[axis] for point in points) for axis in range(3))),
    )


def normalize(objects: list[bpy.types.Object], target_height: float, source_version: str) -> tuple[Vector, Vector]:
    minimum, maximum = bounds(objects)
    source_height = maximum.z - minimum.z
    if source_height <= 0:
        raise RuntimeError("Rodin mesh has zero height")
    factor = target_height / source_height
    for obj in objects:
        obj.scale *= factor
    bpy.context.view_layer.update()
    minimum, maximum = bounds(objects)
    offset = Vector((-(minimum.x + maximum.x) * 0.5, -(minimum.y + maximum.y) * 0.5, -minimum.z))
    for obj in objects:
        obj.location += offset
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        obj.select_set(False)
        obj["source_generator"] = "Hyper3D Rodin"
        obj["source_version"] = source_version
        obj["runtime_export_allowed"] = False
    bpy.context.view_layer.update()
    return bounds(objects)


def reveal(objects: list[bpy.types.Object]) -> None:
    for collection in bpy.data.collections:
        collection.hide_render = False
        collection.hide_viewport = False
    for layer in bpy.context.scene.view_layers:
        def visit(node: bpy.types.LayerCollection) -> None:
            node.exclude = False
            node.hide_viewport = False
            for child in node.children:
                visit(child)
        visit(layer.layer_collection)
    for obj in objects:
        obj.hide_render = False
        obj.hide_viewport = False
        obj.hide_set(False)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def camera(name: str, location: Vector, target: Vector, scale: float) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = scale
    data.clip_start = 0.01
    data.clip_end = 100.0
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def cameras(minimum: Vector, maximum: Vector) -> dict[str, bpy.types.Object]:
    center = (minimum + maximum) * 0.5
    height = maximum.z - minimum.z
    distance = max(maximum.x - minimum.x, maximum.y - minimum.y, height) * 2.8
    scale = height * 1.12
    return {
        "front": camera("CAM_front", Vector((center.x, center.y - distance, center.z)), center, scale),
        "character_left": camera("CAM_character_left", Vector((center.x + distance, center.y, center.z)), center, scale),
        "back": camera("CAM_back", Vector((center.x, center.y + distance, center.z)), center, scale),
        "character_right": camera("CAM_character_right", Vector((center.x - distance, center.y, center.z)), center, scale),
    }


def configure_workbench() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "SINGLE"
    shading.single_color = (0.56, 0.54, 0.50)
    shading.show_shadows = True
    shading.show_cavity = True
    shading.cavity_type = "WORLD"
    shading.show_specular_highlight = True
    shading.background_type = "VIEWPORT"
    shading.background_color = (0.055, 0.060, 0.075)


def render_views(view_cameras: dict[str, bpy.types.Object], validation_root: Path) -> list[str]:
    configure_workbench()
    scene = bpy.context.scene
    outputs = []
    for name, view_camera in view_cameras.items():
        scene.camera = view_camera
        output = validation_root / f"rodin_{name}_clay.png"
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        outputs.append(str(output))
    return outputs


def export_glb(objects: list[bpy.types.Object], path: Path) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_apply=True, export_materials="EXPORT", export_animations=False,
    )
    bpy.ops.object.select_all(action="DESELECT")


def main() -> None:
    args = arguments()
    asset_root = args.asset_root.resolve()
    source_root = asset_root / "rodin_source"
    processed_root = asset_root / "rodin_processed"
    validation_root = asset_root / "validation"
    for directory in (source_root, processed_root, validation_root):
        directory.mkdir(parents=True, exist_ok=True)
    version = asset_root.name
    clean_scene(args.asset_id)
    source_glb = input_glb(asset_root)
    objects = import_model(source_glb, args.asset_id)
    source_topology = weld(objects)
    minimum, maximum = normalize(objects, args.target_height, version)
    reveal(objects)
    view_cameras = cameras(minimum, maximum)
    outputs = render_views(view_cameras, validation_root)
    normalized_glb = processed_root / f"{args.asset_id}_rodin_{version}_normalized.glb"
    export_glb(objects, normalized_glb)
    blend_path = source_root / f"{args.asset_id}_rodin_{version}.blend"
    bpy.context.scene.camera = view_cameras["front"]
    configure_workbench()
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    report = {
        "schema": "rodin_npc_import_report.v1",
        "asset_id": args.asset_id,
        "input_glb": project_relative(source_glb),
        "source_blend": project_relative(blend_path),
        "normalized_glb": project_relative(normalized_glb),
        "objects": [obj.name for obj in objects],
        "source_topology": source_topology,
        "materials": sorted({mat.name for obj in objects for mat in obj.data.materials if mat}),
        "bounds_min_m": [round(value, 6) for value in minimum],
        "bounds_max_m": [round(value, 6) for value in maximum],
        "height_m": round(maximum.z - minimum.z, 6),
        "feet_grounded": abs(minimum.z) <= 0.00001,
        "source_forward": "-Y assumption pending concept overlay",
        "runtime_export_allowed": False,
        "clay_outputs": [project_relative(path) for path in outputs],
    }
    (asset_root / "rodin_import_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("RODIN_NPC_IMPORT_REPORT", json.dumps(report))


if __name__ == "__main__":
    main()
