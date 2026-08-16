"""Import, inspect, and render a non-destructive Hunyuan result for review."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    return Vector(tuple(min(p[i] for p in points) for i in range(3))), Vector(tuple(max(p[i] for p in points) for i in range(3)))


def topology(objects: list[bpy.types.Object]) -> dict:
    verts = faces = edges = boundary = non_manifold = loose = components = 0
    per_object = []
    for obj in objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.index_update()
        object_components = 0
        seen: set[int] = set()
        for vertex in bm.verts:
            if vertex.index in seen:
                continue
            object_components += 1
            seen.add(vertex.index)
            stack = [vertex]
            while stack:
                current = stack.pop()
                for edge in current.link_edges:
                    neighbor = edge.other_vert(current)
                    if neighbor.index not in seen:
                        seen.add(neighbor.index)
                        stack.append(neighbor)
        entry = {
            "name": obj.name,
            "vertices": len(bm.verts),
            "edges": len(bm.edges),
            "faces": len(bm.faces),
            "boundary_edges": sum(edge.is_boundary for edge in bm.edges),
            "non_manifold_edges": sum(not edge.is_manifold for edge in bm.edges),
            "loose_vertices": sum(not vertex.link_edges for vertex in bm.verts),
            "connected_components": object_components,
        }
        per_object.append(entry)
        verts += entry["vertices"]; edges += entry["edges"]; faces += entry["faces"]
        boundary += entry["boundary_edges"]; non_manifold += entry["non_manifold_edges"]
        loose += entry["loose_vertices"]; components += object_components
        bm.free()
    return {"vertices": verts, "edges": edges, "faces": faces, "boundary_edges": boundary, "non_manifold_edges": non_manifold, "loose_vertices": loose, "connected_components": components, "objects": per_object}


def look_at(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def render_views(objects: list[bpy.types.Object], output: Path) -> list[str]:
    low, high = bounds(objects)
    center = (low + high) * 0.5
    height = high.z - low.z
    span = max(high.x - low.x, high.y - low.y, height)
    distance = span * 2.6
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.render.resolution_x = 768
    bpy.context.scene.render.resolution_y = 768
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.context.scene.display.shading.light = "STUDIO"
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    bpy.context.scene.display.shading.show_shadows = True
    bpy.context.scene.display.shading.show_cavity = True
    bpy.context.scene.display.shading.cavity_type = "WORLD"
    bpy.context.scene.display.shading.background_type = "VIEWPORT"
    bpy.context.scene.display.shading.background_color = (0.055, 0.06, 0.075)
    outputs = []
    for name, offset in (("neg_y", (0, -distance, 0)), ("pos_x", (distance, 0, 0)), ("pos_y", (0, distance, 0)), ("neg_x", (-distance, 0, 0))):
        camera_data = bpy.data.cameras.new(f"CAM_{name}")
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = height * 1.14
        camera = bpy.data.objects.new(f"CAM_{name}", camera_data)
        bpy.context.scene.collection.objects.link(camera)
        camera.location = center + Vector(offset)
        look_at(camera, center)
        bpy.context.scene.camera = camera
        path = output / f"mesh_{name}_clay.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        outputs.append(str(path))
        bpy.data.objects.remove(camera, do_unlink=True)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    glb = args.glb.resolve(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    before = set(bpy.data.objects)
    result = bpy.ops.import_scene.gltf(filepath=str(glb))
    if "FINISHED" not in result:
        raise RuntimeError(f"GLB import did not finish: {result}")
    objects = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if not objects:
        raise RuntimeError("Imported GLB has no mesh objects")
    low, high = bounds(objects)
    material_count = sum(len(obj.material_slots) for obj in objects)
    texture_nodes = sum(1 for obj in objects for slot in obj.material_slots if slot.material and slot.material.node_tree for node in slot.material.node_tree.nodes if node.type == "TEX_IMAGE" and node.image)
    report = {
        "schema": "hunyuan_glb_import_review.v1",
        "glb": str(glb), "glb_sha256": sha256(glb), "glb_bytes": glb.stat().st_size,
        "import_result": "FINISHED", "mesh_object_count": len(objects),
        "bounds": {"min": list(low), "max": list(high), "size": list(high - low)},
        "topology": topology(objects),
        "materials": {"slot_count": material_count, "image_texture_node_count": texture_nodes},
        "renders": render_views(objects, output),
        "scope": "cloud_generated_downstream_output_not_a_reference_lock",
    }
    (output / "mesh_import_review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
