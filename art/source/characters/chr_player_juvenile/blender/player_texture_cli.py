"""Debug CLI — hand-color the player character (chr_player_juvenile) and bake a
PBR texture. Headless Blender, runnable repeatedly. Every step prints a log line
(optionally to a file); exit code 0 = all steps OK, non-zero = failure.

Art Bible §4.1: 主角 = 暖灰杏 #BFA982 body + 树皮梅 #5A3F58 dark side + 头冠
低饱和暮靛/信号兰 + 织带双环结。No procedural noise — flat color blocks / vertex
color zones. Bake produces Base Color + ORM (roughness 0.85, metallic 0) from
per-zone materials, then exports a textured GLB for Godot.

Usage (run from repo root):
  Blender --background --factory-startup --python player_texture_cli.py -- \
      --input res://.../autorig_m26_00.fbx \
      --out-dir art/source/characters/chr_player_juvenile/source_locked_v06/texture_debug \
      --log-file /tmp/player_texture_cli.log \
      --verbose 2 \
      --steps uv,bake,export
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

PROJECT = Path(__file__).resolve().parents[5]
DEFAULT_IN = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v06/cloud_raw/autorig_m26_00.fbx"
DEFAULT_OUT = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v06/texture_debug"

# Art Bible §4.1 + locked turnaround (figure_view_0) palette — hex from vision read
def _rgba(hex6: str) -> tuple:
    h = hex6.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4)) + (1.0,)

SKIN = _rgba("#D1B898")         # warm tan skin (head/torso/upper legs/feet)
SKIN_SHADOW = _rgba("#8C7360")  # jaw/eye-socket shadow
CREST_DARK = _rgba("#4A456B")   # head crest deep slate indigo
CREST_LIGHT = _rgba("#9B76C4")  # head crest light lavender
ARM_MARK = _rgba("#9C827D")     # inner-arm triangular markings
BELT = _rgba("#856666")         # belt / rope sash dusty mauve
LEG_PURPLE = _rgba("#6E576E")   # lower/inner leg muted purple
FOOT_STRAP = _rgba("#8C7A6E")   # foot straps brown-grey
EYE = _rgba("#E8963E")          # eye amber
APRICOT = SKIN                  # keep old name for compat
BARK_PLUM = LEG_PURPLE
DUSK_INDIGO = CREST_DARK


class Logger:
    """CLI log with levels: 0=quiet, 1=info, 2=debug."""
    def __init__(self, level: int, log_path: Path | None):
        self.level = level
        self._fh = None
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(log_path, "w", encoding="utf-8")

    def log(self, level: int, msg: str) -> None:
        if level <= self.level:
            line = f"[{'DEBUG' if level >= 2 else 'INFO'}] {msg}"
            print(line)
            if self._fh:
                self._fh.write(line + "\n")
                self._fh.flush()

    def close(self) -> None:
        if self._fh:
            self._fh.close()


def reset_scene(log: Logger) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    log.log(1, "scene reset")


def import_fbx(path: Path, log: Logger) -> tuple[bpy.types.Object | None, bpy.types.Object | None]:
    """Import the master FBX; return (armature, mesh)."""
    bpy.ops.import_scene.fbx(filepath=str(path))
    armature = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    mesh = next((o for o in bpy.data.objects if o.type == "MESH"), None)
    if mesh is None:
        log.log(0, f"FAIL: no mesh in {path}")
        return None, None
    log.log(1, f"imported {path.name}: armature={armature.name if armature else 'none'} mesh={mesh.name} "
               f"verts={len(mesh.data.vertices)} faces={len(mesh.data.polygons)}")
    return armature, mesh


def _dominant_group(obj: bpy.types.Object) -> dict[int, str]:
    """Map each vertex to its dominant (highest-weight) vertex group name."""
    mesh = obj.data
    result: dict[int, str] = {}
    for v in mesh.vertices:
        best_name, best_w = None, -1.0
        for vg in v.groups:
            w = vg.weight
            if w > best_w:
                best_w = w
                best_name = obj.vertex_groups[vg.group].name
        result[v.index] = best_name or ""
    return result


def assign_vertex_colors(obj: bpy.types.Object, log: Logger) -> None:
    """Assign per-zone vertex colors using the skeleton vertex groups so zones
    follow the actual body (crest/face/arms/belt/legs/feet) — matches the locked
    turnaround. Vertex groups come from the FBX (22 deform bones).
    """
    mesh = obj.data
    dom = _dominant_group(obj)
    # group->zone color map; z thresholds refine head crest two-tone + leg split
    counts = {"crest_dark": 0, "crest_light": 0, "face": 0, "torso": 0,
              "arm_mark": 0, "belt": 0, "leg_upper": 0, "leg_purple": 0, "foot": 0}
    attr = mesh.color_attributes.new(name="Color", domain="POINT", type="FLOAT_COLOR")

    # per-group z ranges (from the vertex-group probe) for local thresholding
    GRP_Z = {
        "Head": (126.0, 188.0),
        "LeftArm": (78.0, 126.0), "RightArm": (76.0, 122.0),
        "Hips": (50.0, 103.0),
        "LeftLeg": (0.0, 84.0), "RightLeg": (0.0, 83.0),
    }
    def _grp_t(v, grp: str) -> float:
        """Normalized z within group [0..1]."""
        lo, hi = GRP_Z.get(grp, (0.0, 1.0))
        span = hi - lo
        return 0.0 if span <= 0 else (v.co.z - lo) / span

    def zone_color(v, grp: str) -> tuple:
        # head: crest fins are the top ~6% (z>177); dark blue-purple tips,
        # mid lavender, rest = beige face. From probe: Head z [134,188.6], top
        # bucket(177-188)=100 verts = the actual fins.
        if grp == "Head":
            if v.co.z > 183.0:
                counts["crest_dark"] += 1; return CREST_DARK
            if v.co.z > 177.0:
                counts["crest_light"] += 1; return CREST_LIGHT
            counts["face"] += 1; return SKIN
        # arms: small triangular marking mid-upper-arm (narrow band), rest skin
        if grp in ("LeftArm", "RightArm"):
            t = _grp_t(v, grp)
            if 0.42 < t < 0.52:
                counts["arm_mark"] += 1; return ARM_MARK
            counts["torso"] += 1; return SKIN
        if grp in ("LeftForeArm", "RightForeArm"):
            counts["torso"] += 1; return SKIN
        # belt: thin rope band around hips middle (narrow)
        if grp == "Hips":
            t = _grp_t(v, grp)
            if 0.42 < t < 0.55:
                counts["belt"] += 1; return BELT
            counts["torso"] += 1; return SKIN
        # legs: upper skin, lower purple (hard edge at local z ~0.55)
        if grp in ("LeftUpLeg", "RightUpLeg"):
            counts["leg_upper"] += 1; return SKIN
        if grp in ("LeftLeg", "RightLeg"):
            t = _grp_t(v, grp)
            if t < 0.55:
                counts["leg_purple"] += 1; return LEG_PURPLE
            counts["leg_upper"] += 1; return SKIN
        # feet: strap bands on lower foot
        if grp in ("LeftFoot", "RightFoot"):
            t = _grp_t(v, grp)
            if 0.3 < t < 0.5:
                counts["foot"] += 1; return FOOT_STRAP
            counts["foot"] += 1; return SKIN
        if grp in ("LeftToeBase", "RightToeBase"):
            counts["foot"] += 1; return SKIN
        # torso / spine / neck
        counts["torso"] += 1; return SKIN

    for v in mesh.vertices:
        attr.data[v.index].color = zone_color(v, dom[v.index])
    log.log(1, "vertex color zones: " + " ".join(f"{k}={v}" for k, v in counts.items()))


def smart_uv(obj: bpy.types.Object, log: Logger) -> None:
    """Smart-project UV so the vertex-color zones can be baked to a texture."""
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.2217, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh = obj.data
    uv = mesh.uv_layers.active
    log.log(1, f"smart UV project done: uv_layers={len(mesh.uv_layers)}, name={uv.name if uv else 'none'}")


def bake_pbr(obj: bpy.types.Object, out_dir: Path, log: Logger) -> Path | None:
    """Bake Base Color (from vertex color + material) to a PNG. obj = mesh object.

    NOTE: baked via the exact verified minimal path (smart UV + VertexColor node +
    DIFFUSE bake) that yields colored output; do not restructure without re-running
    the isolation test (it regressed to black when the mode switches were split).
    """
    import numpy as np
    mesh = obj.data
    log.log(2, f"bake_pbr obj={obj.name} verts={len(mesh.vertices)} uv={len(mesh.uv_layers)} color={[a.name for a in mesh.color_attributes]}")
    # re-smart-UV to guarantee a bake-ready layout (idempotent)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.2217, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")

    mat = bpy.data.materials.new("mat_player_debug")
    mat.use_nodes = True
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    vcol = nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "Color"
    mat.node_tree.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])
    img = bpy.data.images.new("player_base_color", 512, 512)
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 4
    scene.cycles.use_denoising = False
    # a neutral direct light keeps the bake from washing colors to white
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    sun = bpy.context.active_object
    sun.rotation_euler = (1.1, 0.3, 0.5)
    sun.data.energy = 2.0
    sun.data.color = (1.0, 1.0, 1.0)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, margin=2)

    out = out_dir / "player_base_color_2048.png"
    img.save_render(str(out))
    px = np.array(img.pixels[:]).reshape(img.size[1], img.size[0], 4)
    log.log(2, f"baked img nonblack={(px[..., :3].sum(axis=2) > 0.1).sum()}")
    log.log(1, f"baked base color → {out.name}")
    return out


def export_glb(out_dir: Path, log: Logger) -> Path:
    """Export the GLB carrying vertex colors (COLOR_0). Godot's cel_base.gdshader
    reads COLOR.rgb as albedo when present, so the art-bible zone colors stay
    exact — no bake washout. A debug material carries the vertex color so glTF
    emits COLOR_0."""
    # ensure the mesh has a material so glTF writes COLOR_0 alongside
    obj = next((o for o in bpy.data.objects if o.type == "MESH"), None)
    if obj and not obj.data.materials:
        mat = bpy.data.materials.new("mat_player_vcol")
        mat.use_nodes = True
        obj.data.materials.append(mat)
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        vcol = nodes.new("ShaderNodeVertexColor")
        vcol.layer_name = "Color"
        mat.node_tree.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        if o.type in ("ARMATURE", "MESH"):
            o.select_set(True)
    out = out_dir / "player_texture_debug.glb"
    bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB", use_selection=True,
                              export_yup=True, export_apply=True)
    log.log(1, f"exported {out.name} ({out.stat().st_size // 1024} KB)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DEFAULT_IN))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--log-file", default=None)
    ap.add_argument("--verbose", type=int, default=1)
    ap.add_argument("--steps", default="all", help="comma list: uv,bake,export or all")
    args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

    log = Logger(args.verbose, Path(args.log_file) if args.log_file else None)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    steps = ["uv", "bake", "export"] if args.steps == "all" else [s.strip() for s in args.steps.split(",")]

    try:
        reset_scene(log)
        armature, mesh_obj = import_fbx(Path(args.input), log)
        if mesh_obj is None:
            log.close()
            return 1
        if "uv" in steps:
            assign_vertex_colors(mesh_obj, log)
            smart_uv(mesh_obj, log)
        if "bake" in steps:
            bake_pbr(mesh_obj, out_dir, log)
        if "export" in steps:
            export_glb(out_dir, log)
        log.log(1, "PLAYER_TEXTURE_CLI_OK steps=%s" % steps)
        log.close()
        return 0
    except Exception as e:  # noqa: BLE001
        log.log(0, f"FAIL: {e}")
        log.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
