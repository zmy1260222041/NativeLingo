#!/usr/bin/env python3
"""Read-only topology audit for a generated GLB.

Imports the supplied asset into an empty Blender scene and writes only audit
artifacts beside this script. The input GLB is never saved or modified.
"""
import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict, deque

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def f6(v):
    return round(float(v), 6)


def bbox_for_points(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    lo = (min(xs), min(ys), min(zs))
    hi = (max(xs), max(ys), max(zs))
    return lo, hi, math.dist(lo, hi)


def face_edge_orientations(poly):
    vs = list(poly.vertices)
    for a, b in zip(vs, vs[1:] + vs[:1]):
        yield (min(a, b), max(a, b)), (a, b)


def component_report(mesh, obj_name, global_diag):
    verts = mesh.vertices
    polys = mesh.polygons
    edge_to_faces = defaultdict(list)
    face_adjacency = [[] for _ in polys]
    edge_orients = defaultdict(list)
    for p in polys:
        for edge_key, directed in face_edge_orientations(p):
            edge_to_faces[edge_key].append(p.index)
            edge_orients[edge_key].append((p.index, directed))
    for linked_faces in edge_to_faces.values():
        if len(linked_faces) >= 2:
            anchor = linked_faces[0]
            for other in linked_faces[1:]:
                face_adjacency[anchor].append(other)
                face_adjacency[other].append(anchor)

    visited = [False] * len(polys)
    face_components = []
    for start in range(len(polys)):
        if visited[start]:
            continue
        q = deque([start])
        visited[start] = True
        group = []
        while q:
            fi = q.popleft()
            group.append(fi)
            for nxt in face_adjacency[fi]:
                if not visited[nxt]:
                    visited[nxt] = True
                    q.append(nxt)
        face_components.append(group)

    component_index = {}
    reports = []
    area_epsilon = max(global_diag * global_diag * 1e-12, 1e-18)
    for ci, faces in enumerate(face_components):
        face_set = set(faces)
        for fi in faces:
            component_index[fi] = ci
        vertex_ids = set()
        material_counts = Counter()
        area = 0.0
        signed_volume = 0.0
        degenerate = 0
        for fi in faces:
            p = polys[fi]
            vertex_ids.update(p.vertices)
            material_counts[str(p.material_index)] += 1
            area += p.area
            if p.area <= area_epsilon:
                degenerate += 1
            # Fan triangulation preserves signed volume for n-gons.
            pvs = [verts[i].co for i in p.vertices]
            for j in range(1, len(pvs) - 1):
                signed_volume += pvs[0].dot(pvs[j].cross(pvs[j + 1])) / 6.0
        component_edges = []
        boundary = nonmanifold = winding_conflicts = 0
        for edge_key, linked in edge_to_faces.items():
            local = [fi for fi in linked if fi in face_set]
            if not local:
                continue
            component_edges.append(edge_key)
            if len(local) == 1:
                boundary += 1
            elif len(local) > 2:
                nonmanifold += 1
            elif len(local) == 2:
                oa = edge_orients[edge_key]
                directed = [o for fi, o in oa if fi in face_set]
                if len(directed) == 2 and directed[0] == directed[1]:
                    winding_conflicts += 1
        points = [verts[i].co[:] for i in vertex_ids]
        lo, hi, diag = bbox_for_points(points)
        face_count = len(faces)
        # Component categorisation is deliberately conservative: separate large
        # shells can be legitimate clothing/body parts; only tiny islands are
        # called fragments.
        rel_diag = diag / global_diag if global_diag else 0.0
        if face_count <= 8 or rel_diag < 0.002:
            category = "micro_fragment"
        elif face_count <= 80 or rel_diag < 0.01:
            category = "small_fragment"
        elif face_count <= 500 or rel_diag < 0.03:
            category = "medium_island"
        else:
            category = "structural_shell"
        reports.append({
            "object": obj_name, "component_id": ci, "category": category,
            "faces": face_count, "vertices": len(vertex_ids), "edges": len(component_edges),
            "boundary_edges": boundary, "nonmanifold_edges": nonmanifold,
            "winding_conflict_edges": winding_conflicts, "degenerate_faces": degenerate,
            "surface_area": f6(area), "signed_volume": f6(signed_volume),
            "bbox_min": [f6(x) for x in lo], "bbox_max": [f6(x) for x in hi],
            "bbox_diagonal": f6(diag), "relative_bbox_diagonal": f6(rel_diag),
            "materials": dict(material_counts),
        })
    return reports, edge_to_faces, component_index, area_epsilon


def make_component_visualization(objects, reports_by_object, output_png):
    # Change only in-memory imported meshes and render a classification preview.
    mats = {}
    colors = {
        "structural_shell": (0.12, 0.50, 0.92, 1),
        "medium_island": (0.20, 0.82, 0.43, 1),
        "small_fragment": (1.00, 0.60, 0.05, 1),
        "micro_fragment": (0.90, 0.08, 0.18, 1),
    }
    for label, color in colors.items():
        mat = bpy.data.materials.new("audit_" + label)
        mat.diffuse_color = color
        mat.metallic = 0.0
        mat.roughness = 0.58
        mats[label] = mat
    for obj in objects:
        reps = reports_by_object.get(obj.name, [])
        by_ci = {r["component_id"]: r["category"] for r in reps}
        # Recreate component membership to apply color by face. The report
        # stored per-component indices only, so repeat via edge connectivity.
        mesh = obj.data
        edge_to_faces = defaultdict(list)
        for p in mesh.polygons:
            for edge_key, _ in face_edge_orientations(p):
                edge_to_faces[edge_key].append(p.index)
        adj = [[] for _ in mesh.polygons]
        for fs in edge_to_faces.values():
            if len(fs) >= 2:
                for x in fs[1:]:
                    adj[fs[0]].append(x); adj[x].append(fs[0])
        seen = [False] * len(mesh.polygons)
        ci = 0
        for start in range(len(mesh.polygons)):
            if seen[start]: continue
            q = deque([start]); seen[start] = True
            while q:
                f = q.popleft()
                for n in adj[f]:
                    if not seen[n]: seen[n] = True; q.append(n)
                label = by_ci[ci]
                if label not in obj.data.materials[:]:
                    obj.data.materials.append(mats[label])
                mesh.polygons[f].material_index = list(obj.data.materials).index(mats[label])
            ci += 1
    scene = bpy.context.scene
    for existing in list(scene.objects):
        if existing.type == 'LIGHT' or existing.type == 'CAMERA':
            bpy.data.objects.remove(existing, do_unlink=True)
    all_points = [obj.matrix_world @ v.co for obj in objects for v in obj.data.vertices]
    lo, hi, diag = bbox_for_points(all_points)
    center = Vector(((lo[0]+hi[0])/2, (lo[1]+hi[1])/2, (lo[2]+hi[2])/2))
    bpy.ops.object.camera_add(location=(center.x + diag*1.15, center.y - diag*1.25, center.z + diag*0.65))
    cam = bpy.context.object
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = 54
    scene.camera = cam
    for loc, energy, size in [
        ((center.x+diag, center.y-diag, center.z+diag), 1300, diag*0.7),
        ((center.x-diag, center.y-diag*0.4, center.z+diag*0.4), 800, diag*0.8),
        ((center.x, center.y+diag, center.z+diag*0.7), 1000, diag*0.5),
    ]:
        bpy.ops.object.light_add(type='AREA', location=loc)
        light = bpy.context.object; light.data.energy = energy; light.data.shape = 'DISK'; light.data.size = size
        light.rotation_euler = (center - light.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x = 1000; scene.render.resolution_y = 1000; scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = output_png
    scene.world.color = (0.035, 0.035, 0.035)
    scene.render.film_transparent = False
    bpy.ops.render.render(write_still=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output-dir', required=True)
    # Blender leaves its own switches in sys.argv. Only consume the payload
    # after its conventional `--` separator.
    cli_args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(cli_args)
    os.makedirs(args.output_dir, exist_ok=True)
    print('audit:arguments_parsed', flush=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    print('audit:factory_scene_ready', flush=True)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(args.input))
    objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    print('audit:imported_mesh_objects=%d' % len(objects), flush=True)
    all_pts = [o.matrix_world @ v.co for o in objects for v in o.data.vertices]
    lo, hi, global_diag = bbox_for_points(all_pts)
    report = {
        "audit_version": 1,
        "input": os.path.abspath(args.input),
        "input_sha256": None,
        "global_bbox_min": [f6(x) for x in lo], "global_bbox_max": [f6(x) for x in hi],
        "global_bbox_diagonal": f6(global_diag), "objects": [], "components": [],
        "summary": {}, "limitations": [
            "Self-intersection requires robust triangle-triangle testing and is reported separately only as a BVH broad-phase candidate count when practical.",
            "Disconnected components are not inherently invalid: intentional rigid parts, clothing layers, and accessories can be separate shells.",
        ]
    }
    reports_by_object = {}
    totals = Counter()
    all_components = []
    for obj in objects:
        print('audit:object=%s faces=%d' % (obj.name, len(obj.data.polygons)), flush=True)
        mesh = obj.data
        reps, edge_to_faces, component_index, eps = component_report(mesh, obj.name, global_diag)
        reports_by_object[obj.name] = reps
        all_components.extend(reps)
        boundary = sum(1 for fs in edge_to_faces.values() if len(fs) == 1)
        nonmanifold = sum(1 for fs in edge_to_faces.values() if len(fs) > 2)
        loose = sum(1 for fs in edge_to_faces.values() if len(fs) == 0)
        zero_len = sum(1 for e in mesh.edges if (mesh.vertices[e.vertices[0]].co - mesh.vertices[e.vertices[1]].co).length <= max(global_diag*1e-12, 1e-18))
        winding = sum(r['winding_conflict_edges'] for r in reps)
        degenerate = sum(r['degenerate_faces'] for r in reps)
        details = {
            "name": obj.name, "vertices": len(mesh.vertices), "edges": len(mesh.edges), "faces": len(mesh.polygons),
            "triangles_estimated": sum(len(p.vertices)-2 for p in mesh.polygons),
            "boundary_edges": boundary, "nonmanifold_edges": nonmanifold, "loose_edges": loose,
            "zero_length_edges": zero_len, "winding_conflict_edges": winding,
            "degenerate_faces": degenerate, "area_epsilon": eps, "components": len(reps),
        }
        report['objects'].append(details); totals.update(details)
    category_counts = Counter(r['category'] for r in all_components)
    category_faces = Counter()
    for r in all_components: category_faces[r['category']] += r['faces']
    all_components.sort(key=lambda r: r['faces'], reverse=True)
    report['components'] = all_components
    total_faces = sum(o['faces'] for o in report['objects'])
    total_verts = sum(o['vertices'] for o in report['objects'])
    total_edges = sum(o['edges'] for o in report['objects'])
    structural_closed = [r for r in all_components if r['category']=='structural_shell' and r['boundary_edges']==0 and r['nonmanifold_edges']==0]
    report['summary'] = {
        "objects": len(objects), "vertices": total_verts, "edges": total_edges, "faces": total_faces,
        "components": len(all_components), "boundary_edges": sum(o['boundary_edges'] for o in report['objects']),
        "nonmanifold_edges": sum(o['nonmanifold_edges'] for o in report['objects']),
        "winding_conflict_edges": sum(o['winding_conflict_edges'] for o in report['objects']),
        "degenerate_faces": sum(o['degenerate_faces'] for o in report['objects']),
        "zero_length_edges": sum(o['zero_length_edges'] for o in report['objects']),
        "components_by_category": dict(category_counts), "faces_by_category": dict(category_faces),
        "largest_components": all_components[:25],
        "closed_structural_shells": len(structural_closed),
        "direct_reduceface_verdict": "BLOCKED" if sum(o['boundary_edges'] for o in report['objects']) or sum(o['nonmanifold_edges'] for o in report['objects']) else "CONDITIONALLY_READY",
        "verdict_reason": "Open boundaries and/or non-manifold edges must be repaired before topology reduction." if sum(o['boundary_edges'] for o in report['objects']) or sum(o['nonmanifold_edges'] for o in report['objects']) else "No open/non-manifold edges detected; inspect disconnected shells and self-intersections before reduction.",
    }
    # SHA is intentionally obtained without reading any untrusted sidecar data.
    import hashlib
    h = hashlib.sha256()
    with open(args.input, 'rb') as src:
        for chunk in iter(lambda: src.read(1024*1024), b''): h.update(chunk)
    report['input_sha256'] = h.hexdigest()
    with open(os.path.join(args.output_dir, 'topology_audit.json'), 'w') as f:
        json.dump(report, f, indent=2)
    print('audit:json_written', flush=True)
    with open(os.path.join(args.output_dir, 'README.md'), 'w') as f:
        f.write('# Mira A-Pose Hunyuan topology audit\\n\\n')
        f.write('Read-only audit. The source GLB was never rewritten. `component_classification.png` uses blue=structural, green=medium island, orange=small fragment, red=micro fragment.\\n')
    make_component_visualization(objects, reports_by_object, os.path.join(args.output_dir, 'component_classification.png'))
    print('audit:visualization_written', flush=True)


if __name__ == '__main__':
    main()
