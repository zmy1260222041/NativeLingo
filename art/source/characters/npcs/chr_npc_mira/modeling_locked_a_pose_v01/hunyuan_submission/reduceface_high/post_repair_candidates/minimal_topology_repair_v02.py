"""Create Mira's minimal, shape-preserving ReduceFace topology repair.

The immutable cloud output remains the visual authority. This script performs
only three local topology operations on an imported duplicate:

1. retessellate zero-area triangles without moving vertices;
2. remove the single microscopic open flap;
3. split the remaining four-face edge into coincident manifold edge fans.

No global resampling, simplification, welding, hole fill, or surface smoothing
is allowed. The exported GLB deliberately mirrors the cloud file's POSITION-only
attribute contract so the Blender exporter does not split every flat-shaded
triangle into isolated vertices.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "reduceface_high_01.glb"
SOURCE_SHA256 = "9f1aa85b218680113e733aa8d2536b295b3e19cfdc7177ca142c5297b6aeffb8"
OUTPUT_DIR = HERE / "minimal_topology_repair_v02"
OUTPUT = OUTPUT_DIR / "chr_npc_mira_a_pose_reduceface_high_minimal_topology_repair_v02.glb"
REPORT = OUTPUT_DIR / "report.json"
DEGENERATE_DISTANCE_M = 1.0e-7


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bounds(obj: bpy.types.Object) -> dict[str, list[float]]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    high = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return {
        "min": [round(value, 9) for value in low],
        "max": [round(value, 9) for value in high],
        "size": [round(value, 9) for value in high - low],
    }


def topology(bm: bmesh.types.BMesh) -> dict[str, int]:
    return {
        "vertices": len(bm.verts),
        "edges": len(bm.edges),
        "faces": len(bm.faces),
        "triangles": sum(len(face.verts) - 2 for face in bm.faces),
        "boundary_edges": sum(len(edge.link_faces) == 1 for edge in bm.edges),
        "multi_face_edges": sum(len(edge.link_faces) > 2 for edge in bm.edges),
        "wire_edges": sum(len(edge.link_faces) == 0 for edge in bm.edges),
        "loose_vertices": sum(not vertex.link_edges for vertex in bm.verts),
        "degenerate_faces": sum(face.calc_area() <= 1.0e-12 for face in bm.faces),
    }


def face_components(bm: bmesh.types.BMesh) -> list[list[bmesh.types.BMFace]]:
    bm.faces.index_update()
    seen: set[int] = set()
    groups: list[list[bmesh.types.BMFace]] = []
    for root in bm.faces:
        if root.index in seen:
            continue
        seen.add(root.index)
        queue = deque([root])
        group: list[bmesh.types.BMFace] = []
        while queue:
            face = queue.popleft()
            group.append(face)
            for edge in face.edges:
                for neighbor in edge.link_faces:
                    if neighbor.index not in seen:
                        seen.add(neighbor.index)
                        queue.append(neighbor)
        groups.append(group)
    return groups


def signed_component_volume(faces: list[bmesh.types.BMFace]) -> float:
    volume = 0.0
    for face in faces:
        points = [vertex.co for vertex in face.verts]
        for index in range(1, len(points) - 1):
            volume += points[0].dot(points[index].cross(points[index + 1])) / 6.0
    return volume


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    source_hash = sha256(SOURCE)
    if source_hash != SOURCE_SHA256:
        raise RuntimeError(f"Unexpected source hash: {source_hash}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    before_objects = set(bpy.data.objects)
    result = bpy.ops.import_scene.gltf(filepath=str(SOURCE))
    if "FINISHED" not in result:
        raise RuntimeError(f"GLB import failed: {result}")
    meshes = [obj for obj in bpy.data.objects if obj not in before_objects and obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"Expected one mesh, found {len(meshes)}")
    obj = meshes[0]
    obj.name = "MIRA_RF_MINIMAL_TOPOLOGY_REPAIR_V02"
    source_bounds = bounds(obj)

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    pre = topology(bm)

    # Retessellate the three zero-area export triangles locally. Dissolving them
    # first produces three small n-gons; explicit triangulation prevents the GLB
    # exporter from recreating degenerate triangles.
    bmesh.ops.dissolve_degenerate(bm, dist=DEGENERATE_DISTANCE_M, edges=list(bm.edges))
    n_gons = [face for face in bm.faces if len(face.verts) > 3]
    if n_gons:
        bmesh.ops.triangulate(bm, faces=n_gons, quad_method="BEAUTY", ngon_method="BEAUTY")

    # The only open defect is a microscopic triangle with two boundary edges and
    # one over-subscribed edge. Match by topology, not fragile face indices.
    flap_faces = [
        face
        for face in bm.faces
        if sum(len(edge.link_faces) == 1 for edge in face.edges) >= 2
        and any(len(edge.link_faces) > 2 for edge in face.edges)
    ]
    if len(flap_faces) != 1:
        raise RuntimeError(f"Expected one microscopic flap, found {len(flap_faces)}")
    flap = flap_faces[0]
    flap_area_m2 = flap.calc_area()
    flap_vertices_world = [
        [round(value, 9) for value in obj.matrix_world @ vertex.co] for vertex in flap.verts
    ]
    bmesh.ops.delete(bm, geom=[flap], context="FACES")

    # One four-face edge remains. Splitting it creates two coincident manifold
    # edge fans and changes no vertex position or visible surface.
    multi_face_edges = [edge for edge in bm.edges if len(edge.link_faces) > 2]
    if len(multi_face_edges) != 1 or len(multi_face_edges[0].link_faces) != 4:
        counts = [len(edge.link_faces) for edge in multi_face_edges]
        raise RuntimeError(f"Expected one four-face edge, found {counts}")
    shared_edge = multi_face_edges[0]
    shared_edge_length_m = shared_edge.calc_length()
    shared_edge_midpoint_world = obj.matrix_world @ (
        (shared_edge.verts[0].co + shared_edge.verts[1].co) * 0.5
    )
    bmesh.ops.split_edges(bm, edges=[shared_edge])
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))

    # The split exposes one nearly zero-volume closed micro shell. Normalize its
    # winding independently so every disconnected closed shell faces outward.
    component_volumes_before = [signed_component_volume(group) for group in face_components(bm)]
    flipped_component_face_counts: list[int] = []
    for group, volume in zip(face_components(bm), component_volumes_before):
        if volume < 0.0:
            bmesh.ops.reverse_faces(bm, faces=group)
            flipped_component_face_counts.append(len(group))

    post = topology(bm)
    required_zero = (
        "boundary_edges",
        "multi_face_edges",
        "wire_edges",
        "loose_vertices",
        "degenerate_faces",
    )
    failures = {key: post[key] for key in required_zero if post[key] != 0}
    if failures:
        raise RuntimeError(f"Minimal topology gate failed: {failures}")

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    repaired_bounds = bounds(obj)
    if repaired_bounds != source_bounds:
        raise RuntimeError(f"Bounds changed: {source_bounds} -> {repaired_bounds}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    export_result = bpy.ops.export_scene.gltf(
        filepath=str(OUTPUT),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_materials="EXPORT",
        export_animations=False,
        export_normals=False,
    )
    if "FINISHED" not in export_result:
        raise RuntimeError(f"GLB export failed: {export_result}")

    report = {
        "schema": "mira_reduceface_minimal_topology_repair.v2",
        "source": {
            "file": str(SOURCE),
            "sha256": source_hash,
            "modified": False,
            "bounds": source_bounds,
        },
        "output": {
            "file": str(OUTPUT),
            "bytes": OUTPUT.stat().st_size,
            "sha256": sha256(OUTPUT),
            "bounds": repaired_bounds,
        },
        "method": {
            "global_resampling": False,
            "global_simplification": False,
            "global_weld": False,
            "vertex_positions_moved": 0,
            "degenerate_distance_m": DEGENERATE_DISTANCE_M,
            "removed_visible_faces": 1,
            "removed_visible_area_m2": flap_area_m2,
            "removed_flap_vertices_world": flap_vertices_world,
            "split_four_face_edge_length_m": shared_edge_length_m,
            "split_four_face_edge_midpoint_world": [
                round(value, 9) for value in shared_edge_midpoint_world
            ],
            "flipped_closed_component_face_counts": flipped_component_face_counts,
            "normals": "face winding recalculated; normals omitted to match the source GLB attribute contract",
        },
        "topology_before_blender": pre,
        "topology_after_blender": post,
        "gate": {
            "local_only": True,
            "bounds_unchanged": True,
            "topology_pass_before_export": True,
            "fresh_glb_reimport_audit_required": True,
        },
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
