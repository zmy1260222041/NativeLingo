"""Import the Hunyuan3D Pro v3.1 multi-view GLB for Mira into a clean Blender scene,
verify the baked PBR texture is attached (贴好图), normalize, render and export.

Mirrors ``chr_player_juvenile/blender/import_render_hunyuan_v05.py`` (verified v05 runbook)
for Mira v06. The raw Tencent output is a dense AI mesh with a baked 4K PBR material, so
this script does NOT enforce a single closed manifold — it reports topology, explicitly
audits the texture nodes (this is the 贴好图 evidence), and proceeds. Orientation is
resolved later by the Gate A silhouette-IoU mapping, so cameras are named by viewpoint
position (ny/px/py/nx) rather than by a presumed forward axis.

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/characters/npcs/chr_npc_mira/source_locked_v06/import_render_hunyuan_v06.py
"""
from __future__ import annotations

import json
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


def _project_root() -> Path:
    here = Path(__file__).resolve().parent
    for cand in (here, *here.parents):
        if (cand / "CLAUDE.md").exists() and (cand / "art").is_dir():
            return cand
    raise RuntimeError("could not locate NativeLingo repo root (CLAUDE.md)")


PROJECT = _project_root()
V06_ROOT = Path(__file__).resolve().parent
RAW_ROOT = V06_ROOT / "hunyuan_raw"
SOURCE_ROOT = V06_ROOT / "hunyuan_source"
PROCESSED_ROOT = V06_ROOT / "hunyuan_processed"
VALIDATION_ROOT = V06_ROOT / "validation"
INPUT_GLB = RAW_ROOT / "mira_hunyuan_mv_v01.glb"
SOURCE_BLEND = SOURCE_ROOT / "chr_npc_mira_hunyuan_v06.blend"
NORMALIZED_GLB = PROCESSED_ROOT / "chr_npc_mira_hunyuan_v06_normalized.glb"
REPORT_PATH = V06_ROOT / "hunyuan_import_report.json"
TARGET_HEIGHT_M = 1.72


def project_relative(path: Path | str) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def eevee_engine() -> str:
    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    if "BLENDER_EEVEE_NEXT" in engines:
        return "BLENDER_EEVEE_NEXT"
    if "BLENDER_EEVEE" in engines:
        return "BLENDER_EEVEE"
    return "CYCLES"


def clean_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "SCN_chr_npc_mira_hunyuan_v06"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"


def import_model() -> list[bpy.types.Object]:
    if not INPUT_GLB.exists():
        raise FileNotFoundError(INPUT_GLB)
    before = set(bpy.data.objects)
    result = bpy.ops.import_scene.gltf(filepath=str(INPUT_GLB))
    if "FINISHED" not in result:
        raise RuntimeError(f"Hunyuan GLB import failed: {result}")
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if not imported:
        raise RuntimeError("Hunyuan GLB imported without a mesh")
    for index, obj in enumerate(imported):
        obj.name = "HUNYUAN_mira_v06" if index == 0 else f"HUNYUAN_mira_v06_part_{index:02d}"
        obj.hide_render = False
        obj.hide_viewport = False
        obj.hide_set(False)
        obj.display_type = "TEXTURED"
    return imported


def inspect_topology(objects: list[bpy.types.Object]) -> dict[str, int]:
    vertices = faces = non_manifold = loose = components = 0
    for obj in objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.index_update()
        vertices += len(bm.verts)
        faces += len(bm.faces)
        non_manifold += sum(1 for edge in bm.edges if not edge.is_manifold)
        loose += sum(1 for vertex in bm.verts if not vertex.link_edges)
        seen: set[int] = set()
        for vertex in bm.verts:
            if vertex.index in seen:
                continue
            components += 1
            stack = [vertex]
            seen.add(vertex.index)
            while stack:
                current = stack.pop()
                for edge in current.link_edges:
                    neighbor = edge.other_vert(current)
                    if neighbor.index not in seen:
                        seen.add(neighbor.index)
                        stack.append(neighbor)
        bm.free()
    return {
        "vertices": vertices,
        "faces": faces,
        "non_manifold_edges": non_manifold,
        "loose_vertices": loose,
        "connected_components": components,
    }


def inspect_textures(objects: list[bpy.types.Object]) -> dict:
    """Explicit 贴好图 evidence: per-material node/texture audit with image resolutions."""
    materials = []
    for obj in objects:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or mat in (m["name"] for m in materials):
                continue
            if any(mat.name == m["name"] for m in materials):
                continue
            nt = mat.node_tree
            bsdf = None
            if nt:
                bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            image_links = []
            if nt:
                for tex in (n for n in nt.nodes if n.type == "TEX_IMAGE"):
                    img = tex.image
                    image_links.append({
                        "node": tex.name,
                        "image": img.name if img else None,
                        "size": list(img.size) if img else None,
                        "target_socket": (tex.outputs[0].links[0].to_socket.name
                                          if tex.outputs[0].links else None),
                    })
            materials.append({
                "name": mat.name,
                "has_principled_bsdf": bsdf is not None,
                "image_textures": image_links,
                "texture_attached": any(it["image"] for it in image_links),
            })
    return {
        "material_count": len(materials),
        "materials": materials,
        "all_textured": bool(materials) and all(m["texture_attached"] for m in materials),
    }


def world_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    return (
        Vector(tuple(min(point[axis] for point in points) for axis in range(3))),
        Vector(tuple(max(point[axis] for point in points) for axis in range(3))),
    )


def normalize_model(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    minimum, maximum = world_bounds(objects)
    height = maximum.z - minimum.z
    if height <= 0.0:
        raise RuntimeError("Hunyuan mesh has zero height")
    scale = TARGET_HEIGHT_M / height
    for obj in objects:
        obj.scale *= scale
    bpy.context.view_layer.update()
    minimum, maximum = world_bounds(objects)
    offset = Vector((-(minimum.x + maximum.x) * 0.5, -(minimum.y + maximum.y) * 0.5, -minimum.z))
    for obj in objects:
        obj.location += offset
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        obj.select_set(False)
        obj["source_generator"] = "Tencent Hunyuan3D Pro"
        obj["source_model"] = "hy-3d-3.1 (Model=3.1)"
        obj["source_inputs"] = "front + left + back + right (MultiViewImages)"
        obj["source_version"] = "source_locked_v06"
        obj["runtime_export_allowed"] = False
    bpy.context.view_layer.update()
    return world_bounds(objects)


def ensure_visible(objects: list[bpy.types.Object]) -> None:
    for collection in bpy.data.collections:
        collection.hide_render = False
        collection.hide_viewport = False
    for layer in bpy.context.scene.view_layers:
        def reveal(node: bpy.types.LayerCollection) -> None:
            node.exclude = False
            node.hide_viewport = False
            for child in node.children:
                reveal(child)
        reveal(layer.layer_collection)
    for obj in objects:
        obj.hide_render = False
        obj.hide_viewport = False
        obj.hide_set(False)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def make_camera(name: str, location: Vector, target: Vector, ortho_scale: float) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = ortho_scale
    data.clip_start = 0.01
    data.clip_end = 100.0
    camera = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = location
    look_at(camera, target)
    return camera


def build_cameras(minimum: Vector, maximum: Vector) -> dict[str, bpy.types.Object]:
    """Cameras named by viewpoint position; forward axis resolved later by the Gate A IoU mapping."""
    center = (minimum + maximum) * 0.5
    height = maximum.z - minimum.z
    depth = max(maximum.x - minimum.x, maximum.y - maximum.y, height)
    distance = depth * 2.6
    scale = height * 1.14
    return {
        "ny": make_camera("CAM_hy_ny", Vector((center.x, center.y - distance, center.z)), center, scale),
        "px": make_camera("CAM_hy_px", Vector((center.x + distance, center.y, center.z)), center, scale),
        "py": make_camera("CAM_hy_py", Vector((center.x, center.y + distance, center.z)), center, scale),
        "nx": make_camera("CAM_hy_nx", Vector((center.x - distance, center.y, center.z)), center, scale),
    }


def configure_workbench() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.film_transparent = False
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


def render_clay_views(cameras: dict[str, bpy.types.Object]) -> list[str]:
    configure_workbench()
    scene = bpy.context.scene
    outputs = []
    for view, camera in cameras.items():
        scene.camera = camera
        output = VALIDATION_ROOT / f"hunyuan_mv_{view}_clay.png"
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        outputs.append(str(output))
    return outputs


def export_normalized_glb(objects: list[bpy.types.Object]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=str(NORMALIZED_GLB),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_materials="EXPORT",
        export_animations=False,
    )
    bpy.ops.object.select_all(action="DESELECT")


def main() -> None:
    for directory in (SOURCE_ROOT, PROCESSED_ROOT, VALIDATION_ROOT):
        directory.mkdir(parents=True, exist_ok=True)
    clean_scene()
    model_objects = import_model()
    source_topology = inspect_topology(model_objects)
    texture_audit = inspect_textures(model_objects)
    minimum, maximum = normalize_model(model_objects)
    ensure_visible(model_objects)
    cameras = build_cameras(minimum, maximum)
    clay_outputs = render_clay_views(cameras)
    export_normalized_glb(model_objects)
    bpy.context.scene.camera = cameras["ny"]
    configure_workbench()
    bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE_BLEND), check_existing=False)
    report = {
        "schema": "hunyuan_v06_import_report.v1",
        "asset_id": "chr_npc_mira",
        "input_glb": project_relative(INPUT_GLB),
        "source_blend": project_relative(SOURCE_BLEND),
        "normalized_glb": project_relative(NORMALIZED_GLB),
        "objects": [obj.name for obj in model_objects],
        "vertices": sum(len(obj.data.vertices) for obj in model_objects),
        "faces": sum(len(obj.data.polygons) for obj in model_objects),
        "source_topology": source_topology,
        "texture_audit": texture_audit,
        "materials": sorted({material.name for obj in model_objects for material in obj.data.materials if material}),
        "bounds_min_m": [round(value, 6) for value in minimum],
        "bounds_max_m": [round(value, 6) for value in maximum],
        "height_m": round(maximum.z - minimum.z, 6),
        "target_height_m": TARGET_HEIGHT_M,
        "source_forward": "TBD (resolved by Gate A silhouette-IoU mapping)",
        "runtime_export_allowed": False,
        "clay_outputs": [project_relative(path) for path in clay_outputs],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("HUNYUAN_V06_IMPORT_REPORT", json.dumps(report))


main()
