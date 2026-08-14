"""One-off preview renders of the v1.5 stylized assets (tree + facet rocks).
Renders each asset 3/4 view with §3.2-class lighting; uses the review
conventions from render_settlement_review.py (vcol wired into Principled)."""
import bpy
import math
import os

REPO = "/Users/a86138/Developer/NativeLingo"
GLB_DIR = os.path.join(REPO, "art/source/environment/env_market_corner/export")
OUT_DIR = os.path.join(REPO, "/tmp".lstrip("/"), "stylized_preview")
OUT_DIR = "/tmp/stylized_preview"

ASSETS = [
    ("fol_tree_stranger_a.glb", "lod0__tree_a", (0.0, 0.0, 0.0), 6.2, 2.4),
    ("env_rock_facet_a.glb", "lod0__rock_a", (0.0, 0.0, 0.0), 2.6, 0.6),
    ("env_rock_facet_b.glb", "lod0__rock_b", (0.0, 0.0, 0.0), 3.0, 0.5),
]


def wire_vertex_colors(obj):
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        nt = mat.node_tree
        if any(n.type == 'MIX' for n in nt.nodes):
            continue
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        vcol = nt.nodes.new('ShaderNodeVertexColors')
        vcol.layer_name = "Color"
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.inputs[7].default_value = (1, 1, 1, 1)   # A (base color)
        mix.inputs[6].default_value = (1, 1, 1, 1)   # B
        mix.blend_type = 'MULTIPLY'
        nt.links.new(vcol.outputs['Color'], mix.inputs[6])
        base_socket = next(l.from_socket for l in nt.links if l.to_socket == bsdf.inputs['Base Color'])
        nt.links.new(base_socket, mix.inputs[7])
        nt.links.new(mix.outputs[2], bsdf.inputs['Base Color'])


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for i, (glb, root_prefix, loc, dist, target_h) in enumerate(ASSETS):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.join(GLB_DIR, glb))
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and obj.name.startswith("lod0__"):
                wire_vertex_colors(obj)
        bpy.ops.object.light_add(type='SUN', location=(0, 0, 0))
        sun = bpy.context.active_object
        sun.rotation_euler = (math.radians(50), math.radians(18), math.radians(25))
        sun.data.energy = 3.4
        sun.data.color = (1.0, 0.95, 0.86)
        bpy.ops.object.light_add(type='SUN', location=(0, 0, 0))
        fill = bpy.context.active_object
        fill.rotation_euler = (math.radians(-40), 0, math.radians(200))
        fill.data.energy = 0.5
        fill.data.color = (0.35, 0.45, 0.5)
        world = bpy.data.worlds.new("W")
        bpy.context.scene.world = world
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        bg.inputs["Color"].default_value = (0.88, 0.85, 0.78, 1.0)
        bg.inputs["Strength"].default_value = 1.0

        ang = math.radians(35)
        cam_loc = (loc[0] + dist * math.sin(ang), loc[1] - dist * math.cos(ang), target_h + dist * 0.28)
        bpy.ops.object.camera_add(location=cam_loc)
        cam = bpy.context.active_object
        cam.data.lens = 50
        focus = mathutils.Vector((loc[0], loc[1], target_h))
        direction = focus - cam.location
        cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        bpy.context.scene.camera = cam

        scene = bpy.context.scene
        scene.render.engine = 'BLENDER_EEVEE'
        scene.render.resolution_x = 860
        scene.render.resolution_y = 1000
        scene.render.image_settings.file_format = 'PNG'
        out = os.path.join(OUT_DIR, glb.replace(".glb", ".png"))
        scene.render.filepath = out
        scene.eevee.taa_render_samples = 48
        scene.view_settings.view_transform = 'Standard'
        bpy.ops.render.render(write_still=True)
        print("PREVIEW_DONE %s" % out)


import mathutils  # noqa: E402

if __name__ == "__main__":
    main()
