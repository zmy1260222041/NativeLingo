# NPC Rodin source-locked pipeline

> This is the only valid Mira, Rowan and Ori modeling route. Rodin provides a sculptable
> Gate A mesh; Blender performs deterministic visibility repair, normalization,
> validation and later sculpt/retopology. Do not rebuild these characters from
> primitives or use rejected turnaround versions.

## Locked inputs

- Mira: `chr_npc_mira/source_locked_v06/reference/figure_view_{0,1,2,3}.png`.
- Rowan: `chr_npc_rowan/source_locked_v04/reference/figure_view_{0,1,2,3}.png`.
- Ori: `chr_npc_ori/source_locked_v06/reference/figure_view_{0,1,2,3}.png`
  after `target_height_m` is approved.
- View order is front, exact character-left, back, exact character-right.
- Each submission set is 512×1024 RGB on a clean Dust-Cream background, shares one
  vertical scale and contains no adjacent figure. Matching `_rgba.png` files and
  masks remain audit-only because the built-in trial endpoint rejects RGBA inputs.
  `reference/registration_report.json` records every deterministic crop, hash
  and audited sole-reconstruction metric.

The old split sets are deleted. The earlier line-run eraser removed sole pixels;
the intermediate v02 repair restored them but left fine guide fragments in toe gaps
and near heel edges. The promoted v03 repair now lives directly in `reference/`,
reconstructs only the contaminated rows, changes zero source pixels outside that
band, and passes a zero-residual connected-fragment gate in all 12 views.

The immutable RGB PNG files are both the submission inputs and the validation
authority. Do not create JPEG proxy copies: the failed MCP adapter rejected both
formats, while the successful route read these PNG bytes directly inside Blender.

## Generate the registered inputs again

```bash
python3 art/source/characters/npcs/blender/prepare_rodin_views.py \
  --config art/source/characters/npcs/chr_npc_mira/source_locked_v06/source_part_seed_manifest_v03.json
python3 art/source/characters/npcs/blender/prepare_rodin_views.py \
  --config art/source/characters/npcs/chr_npc_rowan/source_locked_v04/source_part_seed_manifest_v03.json
python3 art/source/characters/npcs/blender/prepare_rodin_views.py \
  --config art/source/characters/npcs/chr_npc_ori/source_locked_v06/source_part_seed_manifest_v03.json
```

The Python environment must provide Pillow and NumPy.

## Rodin submission — built-in trial route used in this run

The Blender Copilot addon contains a public `Set Free Trial API Key` operator. This
is the route that does not require the user to type a private key:

```python
import bpy
bpy.context.scene.copilot_use_hyper3d = True
bpy.ops.copilot.set_hyper3d_free_trial_key()
```

The current MCP path-to-image adapter returned `Unsupported or invalid image` for
both RGB PNG and JPEG inputs. The working fallback reads the locked image bytes
inside Blender and invokes the addon's executor directly:

```python
from pathlib import Path
import bpy

root = Path("/absolute/path/to/source_locked/reference")
images = [(".png", (root / f"figure_view_{index}.png").read_bytes()) for index in range(4)]
response = bpy.types.copilot_server.executor.cmd_create_rodin_job(images=images)
```

The addon trial executor currently submits one Sketch/Raw job containing the four
images. It does not expose an explicit `condition_mode`; side/back views therefore
remain mandatory Gate A evidence even though the returned mesh is a single model.
Never copy the embedded trial key into the repository, terminal history or reports.

## Clean Blender import and evidence

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python art/source/characters/npcs/blender/import_render_rodin_npc.py -- \
  --asset-root art/source/characters/npcs/chr_npc_mira/source_locked_v06 \
  --asset-id chr_npc_mira --target-height 1.72

/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python art/source/characters/npcs/blender/import_render_rodin_npc.py -- \
  --asset-root art/source/characters/npcs/chr_npc_rowan/source_locked_v04 \
  --asset-id chr_npc_rowan --target-height 2.08
```

The importer always starts from factory state, reveals all object/collection/layer
visibility, welds coincident attribute splits, recalculates normals, grounds the
feet at `z=0`, renders four Workbench clay views, saves an editable `.blend`, exports
a normalized GLB, and writes `rodin_import_report.json`. The normalized GLB remains
`runtime_export_allowed=false`.

## Gate A

The existing Mira and Rowan Rodin results are invalidated because they were created
from the defective legacy reference set. Resubmit the root `reference` images before
starting a new Gate A review. Each new generated result fails Gate A until its four
clay views are compared against the masks and every manifest feature is checked.
Rodin hallucinations must be
sculpted out on the imported base. Retopology, rigging, animation, LOD and Godot
runtime replacement stay blocked until the silhouette/landmark review passes.

Cross-character sculpt, retopology, rig, LOD and Godot rules are authoritative in
`design/art/character-modeling-standard.md`.
