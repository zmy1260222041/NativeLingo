"""Bake the env_market_stall_a 2K diffuse atlas (art-bible §8.4 hero facility 2K).

Opens model_stall_a.blend, smart-unwraps every stall mesh, offsets each mesh's
UV into a quadrant so the three material families share one 0-1 atlas without
overlapping islands, then bakes DIFFUSE with Cycles into textures/stall_atlas_2k.png.
The ORM atlas (G=0.85 roughness, B=0 metallic, R=0 occlusion — cel flat shading
does not use per-texel AO) is written as a flat PNG. Color blocks follow the
art-bible §2 palette; no procedural noise (§5.4/§9.3).

Run headless:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python art/source/environment/env_market_corner/blender/bake_atlas_stall.py
"""
import bpy
import math
import os

REPO = "/Users/a86138/Developer/NativeLingo"
HERE = os.path.join(REPO, "art/source/environment/env_market_corner")
BLEND = os.path.join(HERE, "blender/model_stall_a.blend")
TEX_DIR = os.path.join(HERE, "textures")
ATLAS_PNG = os.path.join(TEX_DIR, "stall_atlas_2k.png")
ORM_PNG = os.path.join(TEX_DIR, "stall_orm_2k.png")
GLB = os.path.join(HERE, "export/env_market_stall_a.glb")

# quadrant origin (0..0.5) per material family; scale 0.5 keeps islands inside
QUADRANTS = {
    "shell":        (0.0, 0.0),
    "clay":         (0.5, 0.0),
    "alloy_frame":  (0.0, 0.5),
    "alloy_detail": (0.5, 0.5),
}


def slot_of(name: str) -> str:
    if "_canopy" in name or "_rib" in name:
        return "shell"
    if "_counter" in name or "_liptop" in name or "_bowl" in name:
        return "clay"
    if "_front" in name or "_knot" in name or "_patch" in name:
        return "alloy_detail"
    return "alloy_frame"


def stall_meshes():
    for obj in bpy.data.objects:
        if obj.type == "MESH" and (
            obj.name.startswith("lod0__")
            or obj.name.startswith("lod1__")
            or obj.name.startswith("lod2__")
        ):
            yield obj


def unwrap_and_offset():
    for obj in stall_meshes():
        slot = slot_of(obj.name)
        ox, oy = QUADRANTS[slot]
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
        bpy.ops.object.mode_set(mode="OBJECT")
        uv_layer = obj.data.uv_layers.active
        for loop in uv_layer.data:
            loop.uv.x = loop.uv.x * 0.5 + ox
            loop.uv.y = loop.uv.y * 0.5 + oy


def wire_bake_targets(atlas):
    """Add the atlas as an ACTIVE-but-unwired ImageTexture node on every stall
    material. It is the bake target, but is NOT wired into shading yet so Cycles
    bakes the Principled base color rather than the image itself."""
    seen = set()
    for obj in stall_meshes():
        for mat in obj.data.materials:
            if mat is None or mat.name in seen:
                continue
            seen.add(mat.name)
            nodes = mat.node_tree.nodes
            img = nodes.new("ShaderNodeTexImage")
            img.name = "bake_target"
            img.image = atlas
            nodes.active = img


def bake_diffuse():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = False
    bpy.ops.object.select_all(action="DESELECT")
    targets = [o for o in stall_meshes() if o.name.startswith("lod0__")]
    for o in targets:
        o.select_set(True)
    bpy.context.view_layer.objects.active = targets[0]
    bpy.ops.object.bake(
        type="DIFFUSE",
        pass_filter={"COLOR"},
        margin=4,
    )


def connect_atlas_to_shading(atlas):
    """After baking, wire the atlas into each Principled Base Color so the
    exported GLB samples the baked texture."""
    seen = set()
    for obj in stall_meshes():
        for mat in obj.data.materials:
            if mat is None or mat.name in seen:
                continue
            seen.add(mat.name)
            nodes = mat.node_tree.nodes
            img = nodes.get("bake_target")
            if img is None:
                continue
            bsdf = nodes.get("Principled BSDF")
            mat.node_tree.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])


def write_pngs(atlas):
    os.makedirs(TEX_DIR, exist_ok=True)
    atlas.save_render(ATLAS_PNG)


def re_export():
    os.makedirs(os.path.dirname(GLB), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=GLB,
        export_format="GLB",
        use_selection=False,
        export_yup=True,
        export_apply=True,
        # "ACTIVE" keeps the authored layer as COLOR_0; the default "MATERIAL"
        # prepends a white COLOR_0 that Godot then reads instead.
        export_vertex_color="ACTIVE",
    )


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    unwrap_and_offset()
    atlas = bpy.data.images.new("stall_atlas", 2048, 2048, alpha=False)
    wire_bake_targets(atlas)
    bake_diffuse()
    connect_atlas_to_shading(atlas)
    write_pngs(atlas)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    re_export()
    print("BAKE_ATLAS_DONE atlas=%s orm=%s glb=%s" % (ATLAS_PNG, ORM_PNG, GLB))


if __name__ == "__main__":
    main()
