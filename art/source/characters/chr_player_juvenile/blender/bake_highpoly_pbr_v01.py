"""Bake the player Hunyuan appearance onto the production LOD0 topology.

This mirrors Mira's verified selected-to-active texture pass:

* the immutable Hunyuan GLB is the visual/material source;
* the immutable ReduceFace-high GLB is the geometry/UV target;
* Base Color, OpenGL tangent-space Normal, and AO are baked at 2K;
* no vertex position or topology may change;
* a textured template GLB and four-view previews are kept with the source;
* the three runtime PNGs are copied into ``game/assets/characters``.

The skinned player FBX has the exact same polygon/vertex indexing as the
ReduceFace-high target. ``retarget_mixamo_actions.py`` transfers this UV map by
loop index when it rebuilds the animated runtime FBX.

Run from the repository root:

    /Applications/Blender.app/Contents/MacOS/Blender --background \
      --factory-startup \
      --python art/source/characters/chr_player_juvenile/blender/bake_highpoly_pbr_v01.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


PROJECT = Path(__file__).resolve().parents[5]
CHAR_ROOT = PROJECT / "art/source/characters/chr_player_juvenile"
HIGH = CHAR_ROOT / "source_locked_v05/hunyuan_processed/hunyuan_multiview_v3_1_normalized.glb"
LOW = CHAR_ROOT / "source_locked_v06/cloud_raw/reduceface_high_01.glb"
HIGH_SHA256 = "8374890393273a2f29c6b07311d0ab50a400afb22339df93031cb792af9e31c0"
LOW_SHA256 = "6ab153fd42eef234992d556bea0d09fedf056ca97b94a6a17327b6db9ee4c547"

OUTPUT_DIR = CHAR_ROOT / "source_locked_v06/baked_pbr_v01"
SOURCE_GLB = OUTPUT_DIR / "chr_player_juvenile_lod0_baked_pbr_v01.glb"
SOURCE_BLEND = OUTPUT_DIR / "chr_player_juvenile_lod0_baked_pbr_v01.blend"
REPORT = OUTPUT_DIR / "bake_report.json"
UV_TRANSFER = OUTPUT_DIR / "chr_player_juvenile_lod0_uv_transfer.json"

BASE_COLOR_NAME = "chr_player_juvenile_base_color_2k.png"
NORMAL_NAME = "chr_player_juvenile_normal_2k.png"
AO_NAME = "chr_player_juvenile_ao_2k.png"
BASE_COLOR = OUTPUT_DIR / BASE_COLOR_NAME
NORMAL = OUTPUT_DIR / NORMAL_NAME
AO = OUTPUT_DIR / AO_NAME
GAME_TEXTURE_DIR = PROJECT / "game/assets/characters"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolution", type=int, default=2048)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--preview-resolution", type=int, default=768)
    argv = __import__("sys").argv
    args = argv[argv.index("--") + 1 :] if "--" in argv else []
    return parser.parse_args(args)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_source(path: Path, expected: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(
            f"Source lock changed: {path}\nexpected={expected}\nactual={actual}"
        )


def project_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT).as_posix()


def import_single_mesh(path: Path, name: str) -> bpy.types.Object:
    before = set(bpy.data.objects)
    result = bpy.ops.import_scene.gltf(filepath=str(path))
    if "FINISHED" not in result:
        raise RuntimeError(f"Import failed for {path}: {result}")
    meshes = [
        obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"
    ]
    if len(meshes) != 1:
        raise RuntimeError(f"Expected one mesh in {path}, found {len(meshes)}")
    obj = meshes[0]
    obj.name = name
    return obj


def world_bounds(obj: bpy.types.Object) -> dict[str, list[float]]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    high = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return {
        "min": [round(value, 9) for value in low],
        "max": [round(value, 9) for value in high],
        "size": [round(value, 9) for value in high - low],
    }


def vertex_positions(obj: bpy.types.Object) -> list[tuple[float, float, float]]:
    return [tuple(vertex.co) for vertex in obj.data.vertices]


def topology_summary(obj: bpy.types.Object) -> dict[str, int]:
    return {
        "vertices": len(obj.data.vertices),
        "edges": len(obj.data.edges),
        "faces": len(obj.data.polygons),
        "triangles": sum(len(face.vertices) - 2 for face in obj.data.polygons),
    }


def surface_alignment(
    source: bpy.types.Object, target: bpy.types.Object
) -> dict[str, float]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(source, depsgraph)
    source_inverse = source.matrix_world.inverted()
    distances: list[float] = []
    for vertex in target.data.vertices:
        world = target.matrix_world @ vertex.co
        nearest = bvh.find_nearest(source_inverse @ world)
        if nearest is None:
            raise RuntimeError("BVH nearest-surface query failed")
        source_world = source.matrix_world @ nearest[0]
        distances.append((source_world - world).length)
    ordered = sorted(distances)

    def percentile(fraction: float) -> float:
        index = min(
            len(ordered) - 1,
            int(round((len(ordered) - 1) * fraction)),
        )
        return ordered[index]

    result = {
        "mean_m": sum(ordered) / len(ordered),
        "p95_m": percentile(0.95),
        "p99_m": percentile(0.99),
        "max_m": ordered[-1],
    }
    if result["p99_m"] > 0.02 or result["max_m"] > 0.05:
        raise RuntimeError(f"High/low surfaces are not aligned closely enough: {result}")
    return result


def create_uv(target: bpy.types.Object) -> dict[str, object]:
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    while len(target.data.uv_layers) > 0:
        target.data.uv_layers.remove(target.data.uv_layers[0])
    target.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(
        angle_limit=math.radians(66.0),
        island_margin=0.012,
        area_weight=0.0,
        correct_aspect=True,
        scale_to_bounds=True,
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    uv_layer = target.data.uv_layers.active
    coords = [loop.uv.copy() for loop in uv_layer.data]
    if not coords:
        raise RuntimeError("UV unwrap produced no loop coordinates")
    low = [min(uv[index] for uv in coords) for index in range(2)]
    high = [max(uv[index] for uv in coords) for index in range(2)]
    if (
        low[0] < -1.0e-5
        or low[1] < -1.0e-5
        or high[0] > 1.00001
        or high[1] > 1.00001
    ):
        raise RuntimeError(f"UV coordinates are outside 0..1: {low} -> {high}")
    return {
        "name": uv_layer.name,
        "loop_count": len(coords),
        "min": [round(value, 7) for value in low],
        "max": [round(value, 7) for value in high],
    }


def write_uv_transfer(target: bpy.types.Object) -> dict[str, object]:
    """Persist UVs without glTF's seam-driven vertex duplication.

    The AutoRig FBX preserves the ReduceFace polygon and vertex ordering. A
    compact per-polygon loop map lets the retarget pipeline copy UV0 onto the
    skinned mesh while retaining that original topology contract.
    """
    uv_layer = target.data.uv_layers.active
    if uv_layer is None:
        raise RuntimeError("Cannot write UV transfer data without an active UV layer")
    faces = []
    for polygon in target.data.polygons:
        faces.append(
            {
                "vertices": list(polygon.vertices),
                "uv": [
                    [
                        round(uv_layer.data[loop_index].uv.x, 9),
                        round(uv_layer.data[loop_index].uv.y, 9),
                    ]
                    for loop_index in polygon.loop_indices
                ],
            }
        )
    payload = {
        "schema": "player_lod0_uv_transfer.v1",
        "source": project_relative(LOW),
        "vertices": len(target.data.vertices),
        "faces": len(target.data.polygons),
        "loops": len(uv_layer.data),
        "uv_layer": uv_layer.name,
        "polygons": faces,
    }
    UV_TRANSFER.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return {
        "file": project_relative(UV_TRANSFER),
        "bytes": UV_TRANSFER.stat().st_size,
        "sha256": sha256(UV_TRANSFER),
        "vertices": payload["vertices"],
        "faces": payload["faces"],
        "loops": payload["loops"],
    }


def create_image(
    name: str,
    resolution: int,
    color: tuple[float, float, float, float],
    non_color: bool,
) -> bpy.types.Image:
    image = bpy.data.images.new(
        name=name,
        width=resolution,
        height=resolution,
        alpha=False,
        float_buffer=False,
    )
    image.generated_color = color
    image.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    return image


def create_bake_material(
    target: bpy.types.Object,
) -> tuple[bpy.types.Material, bpy.types.ShaderNodeTexImage]:
    material = bpy.data.materials.new("MAT_Player_Bake_Target")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (300, 0)
    principled = nodes.new(type="ShaderNodeBsdfPrincipled")
    principled.location = (0, 0)
    image_node = nodes.new(type="ShaderNodeTexImage")
    image_node.location = (-350, 0)
    material.node_tree.links.new(
        principled.outputs["BSDF"], output.inputs["Surface"]
    )
    target.data.materials.clear()
    target.data.materials.append(material)
    return material, image_node


def select_for_bake(source: bpy.types.Object, target: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    source.hide_render = False
    source.hide_set(False)
    source.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target


def bake_map(
    source: bpy.types.Object,
    target: bpy.types.Object,
    image_node: bpy.types.ShaderNodeTexImage,
    image: bpy.types.Image,
    filepath: Path,
    bake_type: str,
    ray_distance: float,
    margin: int,
) -> dict[str, object]:
    image_node.image = image
    for node in image_node.id_data.nodes:
        node.select = False
    image_node.select = True
    image_node.id_data.nodes.active = image_node
    select_for_bake(source, target)
    kwargs: dict[str, object] = {
        "type": bake_type,
        "use_selected_to_active": True,
        "cage_extrusion": min(0.006, max(0.002, ray_distance * 0.20)),
        "max_ray_distance": ray_distance,
        "margin": margin,
        "margin_type": "EXTEND",
        "use_clear": True,
    }
    if bake_type == "DIFFUSE":
        kwargs["pass_filter"] = {"COLOR"}
    if bake_type == "NORMAL":
        kwargs.update(
            {
                "normal_space": "TANGENT",
                "normal_r": "POS_X",
                "normal_g": "POS_Y",
                "normal_b": "POS_Z",
            }
        )
    print(
        f"BAKE_START type={bake_type} resolution={image.size[:]} "
        f"ray_distance={ray_distance:.6f}"
    )
    result = bpy.ops.object.bake(**kwargs)
    if "FINISHED" not in result:
        raise RuntimeError(f"Bake failed for {bake_type}: {result}")
    image.filepath_raw = str(filepath)
    image.file_format = "PNG"
    image.save()
    image.pack()
    channel_samples = list(image.pixels[0 : min(len(image.pixels), 400000) : 4])
    summary = {
        "file": project_relative(filepath),
        "bytes": filepath.stat().st_size,
        "sha256": sha256(filepath),
        "resolution": list(image.size),
        "sampled_red_min": min(channel_samples) if channel_samples else None,
        "sampled_red_max": max(channel_samples) if channel_samples else None,
    }
    print(f"BAKE_DONE type={bake_type} file={filepath}")
    return summary


def create_gltf_output_group() -> bpy.types.ShaderNodeTree:
    name = "glTF Material Output"
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        return existing
    group = bpy.data.node_groups.new(name, "ShaderNodeTree")
    group.interface.new_socket(
        "Occlusion", in_out="INPUT", socket_type="NodeSocketFloat"
    )
    group.nodes.new("NodeGroupOutput")
    input_node = group.nodes.new("NodeGroupInput")
    input_node.location = (-200, 0)
    return group


def create_runtime_material(
    target: bpy.types.Object,
    base_image: bpy.types.Image,
    normal_image: bpy.types.Image,
    ao_image: bpy.types.Image,
) -> bpy.types.Material:
    material = bpy.data.materials.new("mat_chr_player_juvenile_pbr")
    material.use_nodes = True
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (650, 0)
    principled = nodes.new(type="ShaderNodeBsdfPrincipled")
    principled.location = (320, 0)
    principled.inputs["Metallic"].default_value = 0.0
    principled.inputs["Roughness"].default_value = 0.78

    base = nodes.new(type="ShaderNodeTexImage")
    base.name = "Player Base Color"
    base.label = "Base Color (sRGB)"
    base.image = base_image
    base.location = (-650, 180)

    normal = nodes.new(type="ShaderNodeTexImage")
    normal.name = "Player Normal"
    normal.label = "Normal (OpenGL, Non-Color)"
    normal.image = normal_image
    normal.location = (-650, -80)
    normal_map = nodes.new(type="ShaderNodeNormalMap")
    normal_map.space = "TANGENT"
    normal_map.inputs["Strength"].default_value = 1.0
    normal_map.location = (-210, -80)

    ao = nodes.new(type="ShaderNodeTexImage")
    ao.name = "Player AO"
    ao.label = "AO (R, Non-Color)"
    ao.image = ao_image
    ao.location = (-650, -330)
    settings = nodes.new(type="ShaderNodeGroup")
    settings.name = "glTF Material Output"
    settings.label = "glTF Material Output"
    settings.node_tree = create_gltf_output_group()
    settings.location = (-180, -330)

    links.new(base.outputs["Color"], principled.inputs["Base Color"])
    links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
    links.new(ao.outputs["Color"], settings.inputs["Occlusion"])
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    target.data.materials.clear()
    target.data.materials.append(material)
    return material


def export_glb(target: bpy.types.Object, filepath: Path) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    target.hide_render = False
    target.hide_set(False)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    result = bpy.ops.export_scene.gltf(
        filepath=str(filepath),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_animations=False,
        export_normals=True,
        export_tangents=True,
        export_texcoords=True,
        export_yup=True,
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"GLB export failed: {result}")


def point_camera(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def setup_preview_scene(target: bpy.types.Object, resolution: int) -> bpy.types.Object:
    for obj in list(bpy.data.objects):
        if obj != target and obj.type in {"LIGHT", "CAMERA"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.view_settings.look = "AgX - Medium High Contrast"

    world = bpy.data.worlds.get("Player Preview World")
    if world is None:
        world = bpy.data.worlds.new("Player Preview World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.035,
        0.045,
        0.065,
        1.0,
    )
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    for name, location, energy, size, color in [
        ("Key", (2.2, -2.8, 2.8), 850.0, 2.0, (1.0, 0.88, 0.72)),
        ("Fill", (-2.5, -1.0, 1.8), 420.0, 2.6, (0.62, 0.78, 1.0)),
        ("Rim", (0.5, 2.6, 2.4), 700.0, 1.6, (0.55, 0.88, 1.0)),
    ]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = color
        light = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(light)
        light.location = location
        point_camera(light, Vector((0.0, 0.0, 0.89)))

    camera_data = bpy.data.cameras.new("Player Preview Camera")
    camera = bpy.data.objects.new("Player Preview Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 2.08
    scene.camera = camera
    return camera


def render_previews(target: bpy.types.Object, resolution: int) -> list[str]:
    camera = setup_preview_scene(target, resolution)
    center = Vector((0.0, 0.0, 0.89))
    views = {
        "front": Vector((0.0, -3.0, 0.96)),
        "character_left": Vector((3.0, 0.0, 0.96)),
        "back": Vector((0.0, 3.0, 0.96)),
        "character_right": Vector((-3.0, 0.0, 0.96)),
    }
    rendered: list[str] = []
    for name, location in views.items():
        camera.location = location
        point_camera(camera, center)
        output = OUTPUT_DIR / f"preview_{name}.png"
        bpy.context.scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        rendered.append(project_relative(output))
    return rendered


def copy_runtime_maps() -> dict[str, str]:
    GAME_TEXTURE_DIR.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    for label, source in [
        ("base_color", BASE_COLOR),
        ("normal", NORMAL),
        ("ao", AO),
    ]:
        destination = GAME_TEXTURE_DIR / source.name
        shutil.copy2(source, destination)
        outputs[label] = project_relative(destination)
    return outputs


def main() -> None:
    args = parse_args()
    if args.resolution < 256 or args.resolution > 4096:
        raise ValueError("Resolution must be between 256 and 4096")
    verify_source(HIGH, HIGH_SHA256)
    verify_source(LOW, LOW_SHA256)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    source = import_single_mesh(HIGH, "PLAYER_HUNYUAN_VISUAL_SOURCE_IMMUTABLE")
    target = import_single_mesh(LOW, "PLAYER_LOD0_BAKED_PBR_V01")
    source_bounds = world_bounds(source)
    target_bounds = world_bounds(target)
    positions_before = vertex_positions(target)
    topology_before = topology_summary(target)
    alignment = surface_alignment(source, target)
    ray_distance = min(
        0.04,
        max(
            0.012,
            alignment["p99_m"] * 4.0,
            alignment["max_m"] * 1.25,
        ),
    )

    for polygon in target.data.polygons:
        polygon.use_smooth = True
    uv = create_uv(target)
    uv_transfer = write_uv_transfer(target)
    _, bake_node = create_bake_material(target)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.render.bake.target = "IMAGE_TEXTURES"
    margin = max(8, args.resolution // 128)
    base_image = create_image(
        "chr_player_juvenile_base_color_2k",
        args.resolution,
        (0.04, 0.04, 0.04, 1.0),
        False,
    )
    normal_image = create_image(
        "chr_player_juvenile_normal_2k",
        args.resolution,
        (0.5, 0.5, 1.0, 1.0),
        True,
    )
    ao_image = create_image(
        "chr_player_juvenile_ao_2k",
        args.resolution,
        (1.0, 1.0, 1.0, 1.0),
        True,
    )

    maps = {
        "base_color": bake_map(
            source,
            target,
            bake_node,
            base_image,
            BASE_COLOR,
            "DIFFUSE",
            ray_distance,
            margin,
        ),
        "normal": bake_map(
            source,
            target,
            bake_node,
            normal_image,
            NORMAL,
            "NORMAL",
            ray_distance,
            margin,
        ),
        "ao": bake_map(
            source,
            target,
            bake_node,
            ao_image,
            AO,
            "AO",
            ray_distance,
            margin,
        ),
    }
    create_runtime_material(target, base_image, normal_image, ao_image)

    if vertex_positions(target) != positions_before or world_bounds(target) != target_bounds:
        raise RuntimeError("Geometry changed during the material pass")
    topology_after = topology_summary(target)
    if topology_after != topology_before:
        raise RuntimeError(
            f"Topology changed during the material pass: "
            f"{topology_before} -> {topology_after}"
        )

    source.hide_render = True
    source.hide_set(True)
    export_glb(target, SOURCE_GLB)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE_BLEND))
    previews = render_previews(target, args.preview_resolution)
    runtime_maps = copy_runtime_maps()

    report = {
        "schema": "player_hunyuan_to_runtime_lod0_pbr_bake.v1",
        "source_lock": {
            "high_glb": project_relative(HIGH),
            "high_sha256": HIGH_SHA256,
            "low_glb": project_relative(LOW),
            "low_sha256": LOW_SHA256,
            "high_bounds": source_bounds,
            "low_bounds": target_bounds,
        },
        "method": {
            "reference_pipeline": "Mira selected-to-active PBR bake",
            "selected_to_active": True,
            "resolution": args.resolution,
            "samples": args.samples,
            "ray_distance_m": ray_distance,
            "margin_px": margin,
            "normal_convention": "OpenGL tangent space (+Y / green up)",
            "global_resampling": False,
            "vertex_positions_moved": 0,
            "topology_changed": False,
        },
        "alignment": alignment,
        "uv": uv,
        "uv_transfer": uv_transfer,
        "topology_before": topology_before,
        "topology_after": topology_after,
        "maps": maps,
        "output": {
            "source_glb": project_relative(SOURCE_GLB),
            "source_glb_bytes": SOURCE_GLB.stat().st_size,
            "source_glb_sha256": sha256(SOURCE_GLB),
            "blend": project_relative(SOURCE_BLEND),
            "previews": previews,
            "runtime_maps": runtime_maps,
        },
        "runtime_status": (
            "UV template and PBR maps ready; animated FBX UV transfer is owned by "
            "retarget_mixamo_actions.py"
        ),
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
