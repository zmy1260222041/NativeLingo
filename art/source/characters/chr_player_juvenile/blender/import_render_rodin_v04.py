"""Import the Rodin v04 GLB into a clean Blender scene and render verified views.

The first Rodin attempt rendered from a long-lived interactive scene whose visibility and
view-layer state were not persisted.  This script deliberately starts from an empty scene,
normalizes the raw mesh without modifying the downloaded GLB, creates deterministic cameras,
renders both Workbench clay and EEVEE PBR evidence, then saves a reproducible .blend and GLB.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


PROJECT = Path(__file__).resolve().parents[5]
V04_ROOT = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v04"
RAW_ROOT = V04_ROOT / "rodin_raw"
SOURCE_ROOT = V04_ROOT / "rodin_source"
PROCESSED_ROOT = V04_ROOT / "rodin_processed"
VALIDATION_ROOT = V04_ROOT / "validation"
INPUT_GLB = RAW_ROOT / "base_basic_pbr.glb"
SOURCE_BLEND = SOURCE_ROOT / "chr_player_juvenile_rodin_v04.blend"
NORMALIZED_GLB = PROCESSED_ROOT / "chr_player_juvenile_rodin_v04_normalized.glb"
REPORT_PATH = V04_ROOT / "rodin_import_report.json"
TARGET_HEIGHT_M = 1.78


def project_relative(path: Path | str) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def clean_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "SCN_chr_player_juvenile_rodin_v04"
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
        raise RuntimeError(f"Rodin GLB import failed: {result}")
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if not imported:
        raise RuntimeError("Rodin GLB imported without a mesh")
    for index, obj in enumerate(imported):
        obj.name = "RODIN_model_v04" if index == 0 else f"RODIN_model_v04_part_{index:02d}"
        obj.hide_render = False
        obj.hide_viewport = False
        obj.hide_set(False)
        obj.display_type = "TEXTURED"
    return imported


def weld_source_topology(objects: list[bpy.types.Object]) -> dict[str, int]:
    """Weld Rodin's coincident attribute-split vertices without changing the surface shape."""
    before_vertices = sum(len(obj.data.vertices) for obj in objects)
    for obj in objects:
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.000001)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        bm.free()
        mesh.update(calc_edges=True)
        for polygon in mesh.polygons:
            polygon.use_smooth = True
    topology = inspect_topology(objects)
    topology["vertices_before_weld"] = before_vertices
    if topology["non_manifold_edges"] or topology["connected_components"] != 1:
        raise RuntimeError(f"Rodin weld did not produce one closed manifold: {topology}")
    return topology


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
        raise RuntimeError("Rodin mesh has zero height")
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
        obj["source_generator"] = "Hyper3D Rodin"
        obj["source_version"] = "source_locked_v04"
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
    center = (minimum + maximum) * 0.5
    height = maximum.z - minimum.z
    depth = max(maximum.x - minimum.x, maximum.y - minimum.y, height)
    distance = depth * 2.6
    scale = height * 1.14
    # Rodin output faces -Y.  Keep the raw source orientation until the runtime export stage.
    return {
        "ny": make_camera("CAM_RODIN_front_ny", Vector((center.x, center.y - distance, center.z)), center, scale),
        "px": make_camera("CAM_RODIN_left_px", Vector((center.x + distance, center.y, center.z)), center, scale),
        "py": make_camera("CAM_RODIN_right_py", Vector((center.x - distance, center.y, center.z)), center, scale),
        "nx": make_camera("CAM_RODIN_back_nx", Vector((center.x, center.y + distance, center.z)), center, scale),
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
        output = RAW_ROOT / f"view_{view}.png"
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        outputs.append(str(output))
        validation = VALIDATION_ROOT / f"rodin_{view}_clay.png"
        scene.render.filepath = str(validation)
        bpy.ops.render.render(write_still=True)
        outputs.append(str(validation))
    return outputs


def create_floor() -> bpy.types.Object:
    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, -0.004))
    floor = bpy.context.object
    floor.name = "RENDER_ONLY_floor"
    material = bpy.data.materials.new("MAT_render_floor")
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.035, 0.038, 0.050, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.93
    floor.data.materials.append(material)
    return floor


def create_light(name: str, location: tuple[float, float, float], energy: float,
                 color: tuple[float, float, float], size: float, target: Vector) -> bpy.types.Object:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    light = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(light)
    light.location = location
    look_at(light, target)
    return light


def configure_eevee(center: Vector) -> list[bpy.types.Object]:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("WORLD_rodin_studio")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.018, 0.022, 0.035, 1.0)
    background.inputs["Strength"].default_value = 0.32
    scene.world = world
    floor = create_floor()
    lights = [
        create_light("LGT_key", (-2.8, -3.4, 3.4), 850.0, (1.0, 0.82, 0.67), 2.4, center),
        create_light("LGT_fill", (2.6, -2.2, 2.2), 430.0, (0.64, 0.78, 1.0), 3.0, center),
        create_light("LGT_rim", (0.8, 2.8, 3.0), 720.0, (0.72, 0.67, 1.0), 2.0, center),
    ]
    return [floor, *lights]


def render_beauty(minimum: Vector, maximum: Vector) -> list[str]:
    center = (minimum + maximum) * 0.5
    render_only = configure_eevee(center)
    camera_data = bpy.data.cameras.new("CAM_RODIN_beauty")
    camera_data.type = "PERSP"
    camera_data.lens = 68.0
    camera = bpy.data.objects.new("CAM_RODIN_beauty", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.data.clip_start = 0.01
    camera.data.clip_end = 100.0
    scene = bpy.context.scene
    scene.camera = camera
    outputs = []
    for name, location in (
        ("front", Vector((center.x, center.y - 3.25, center.z + 0.04))),
        ("3qtr", Vector((center.x + 2.35, center.y - 2.75, center.z + 0.14))),
    ):
        camera.location = location
        look_at(camera, Vector((center.x, center.y, center.z - 0.03)))
        output = RAW_ROOT / f"beauty_{name}_v3.png"
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        outputs.append(str(output))
        validation = VALIDATION_ROOT / f"rodin_{name}_pbr.png"
        scene.render.filepath = str(validation)
        bpy.ops.render.render(write_still=True)
        outputs.append(str(validation))
    for obj in render_only:
        obj.hide_render = True
    camera.hide_render = True
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
    source_topology = weld_source_topology(model_objects)
    minimum, maximum = normalize_model(model_objects)
    ensure_visible(model_objects)
    cameras = build_cameras(minimum, maximum)
    clay_outputs = render_clay_views(cameras)
    pbr_outputs = render_beauty(minimum, maximum)
    export_normalized_glb(model_objects)
    bpy.context.scene.camera = cameras["ny"]
    configure_workbench()
    bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE_BLEND), check_existing=False)
    report = {
        "schema": "rodin_v04_import_report.v1",
        "input_glb": project_relative(INPUT_GLB),
        "source_blend": project_relative(SOURCE_BLEND),
        "normalized_glb": project_relative(NORMALIZED_GLB),
        "objects": [obj.name for obj in model_objects],
        "vertices": sum(len(obj.data.vertices) for obj in model_objects),
        "faces": sum(len(obj.data.polygons) for obj in model_objects),
        "source_topology": source_topology,
        "materials": sorted({material.name for obj in model_objects for material in obj.data.materials if material}),
        "bounds_min_m": [round(value, 6) for value in minimum],
        "bounds_max_m": [round(value, 6) for value in maximum],
        "height_m": round(maximum.z - minimum.z, 6),
        "source_forward": "-Y",
        "runtime_export_allowed": False,
        "clay_outputs": [project_relative(path) for path in clay_outputs],
        "pbr_outputs": [project_relative(path) for path in pbr_outputs],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("RODIN_V04_IMPORT_REPORT", json.dumps(report))


main()
