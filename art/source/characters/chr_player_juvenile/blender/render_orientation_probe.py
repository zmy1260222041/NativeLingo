"""Render the exported runtime GLB from 4 ortho cardinal views to diagnose orientation.

Loads game/assets/characters/chr_player_juvenile.glb into a clean Blender scene,
adds a sun + 4 ortho cameras (top/-Z, front/+Y-looking--Y, right/+X, back/-Y), and
renders small PNGs so the actual orientation can be seen. Blender is Z-up, so:
  - TOP cam looks down -Z   (should see the character from above, head near center)
  - FRONT cam looks along -Y (camera at +Y) — Blender's default "front"
  - RIGHT cam looks along -X (camera at +X)
"""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector

PROJECT = Path(__file__).resolve().parents[5]
# render the RAW tencent delivery (autorig idle FBX) to see pristine orientation
GLB = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v06/cloud_raw/autorig_m26_00.fbx"
OUT = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v06/orientation_probe_fbx"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(GLB))

    # find the character root + bounds to frame the cameras
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("no mesh in GLB")
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for o in meshes:
        for c in o.bound_box:
            wc = o.matrix_world @ Vector(c)
            for i in range(3):
                mins[i] = min(mins[i], wc[i]); maxs[i] = max(maxs[i], wc[i])
    center = (mins + maxs) / 2
    size = max(maxs - mins)
    print(f"[probe] bounds min={tuple(round(v,2) for v in mins)} max={tuple(round(v,2) for v in maxs)} center={tuple(round(v,2) for v in center)} size={size:.2f}")
    print(f"[probe] height(Z)={maxs.z-mins.z:.2f} width(X)={maxs.x-mins.x:.2f} depth(Y)={maxs.y-mins.y:.2f}")

    # sun light
    light_data = bpy.data.lights.new("sun", type="SUN")
    light_data.energy = 3.0
    light = bpy.data.objects.new("sun", light_data)
    light.rotation_euler = (0.6, 0.2, 0.4)
    bpy.context.scene.collection.objects.link(light)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 400
    scene.render.resolution_y = 600
    scene.render.image_settings.file_format = "PNG"
    # neutral mid-gray background so silhouette is visible
    scene.world = bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.5, 0.5, 0.55, 1.0)
    bg.inputs[1].default_value = 1.0

    views = [
        ("top", center + Vector((0, 0, size * 1.5)), Vector((0, 0, -1)), Vector((0, 1, 0))),
        ("front", center + Vector((0, size * 2.0, 0)), Vector((0, -1, 0)), Vector((0, 0, 1))),
        ("back", center + Vector((0, -size * 2.0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))),
        ("right", center + Vector((size * 2.0, 0, 0)), Vector((-1, 0, 0)), Vector((0, 0, 1))),
    ]
    for name, loc, look, up in views:
        cam_data = bpy.data.cameras.new(name)
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = size * 1.2
        cam = bpy.data.objects.new(f"cam_{name}", cam_data)
        cam.location = loc
        # point at center
        direction = (Vector(center) - Vector(loc)).normalized()
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.collection.objects.link(cam)
        scene.camera = cam
        scene.render.filepath = str(OUT / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[probe] rendered {name}.png from {tuple(round(v,2) for v in loc)}")


if __name__ == "__main__":
    main()
