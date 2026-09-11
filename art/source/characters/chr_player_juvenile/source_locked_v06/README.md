# Player juvenile — v06 cloud-built runtime candidate

Status: `CLOUD_PIPELINE_COMPLETE / GATE_D_15_of_16 / BLENDSHAPES_PENDING_MANUAL`

The first player runtime asset to reach `game/assets/characters/`. Built
end-to-end from the v05 Hunyuan base via Tencent ai3d cloud jobs + a headless Blender assembly,
with no manual modeling. Triangle budgets all met; 15 of 16 Gate D contract checks pass.

## Pipeline (all stages reproducible from this tree)

Input: `../source_locked_v05/hunyuan_processed/hunyuan_multiview_v3_1_normalized.glb`
(299 293 verts / 500 000 tris, unrigged, with one embedded 4096² Hunyuan Base Color map).

| Stage | ai3d action | Output in `cloud_raw/` | Result |
|---|---|---|---|
| LOD0 | `SubmitReduceFaceJob` FaceLevel=high | `reduceface_high_01.glb` | 11 293 tris (≤32k ✓) |
| LOD1 | `SubmitReduceFaceJob` FaceLevel=medium | `reduceface_medium_01.glb` | 8 905 tris (≤16k ✓) |
| LOD2 | `SubmitReduceFaceJob` FaceLevel=low | `reduceface_low_01.glb` | 5 698 tris (≤6k ✓) |
| Rig + idle | `SubmitAutoRiggingJob` MotionType=26 on LOD0 | `autorig_m26_00.fbx` | 28-bone armature (22 deform) + idle |
| Rig + walk | `SubmitAutoRiggingJob` MotionType=23 on LOD0 | `autorig_m23_00.fbx` | walk action |
| Greet | `SubmitHunyuanTo3DMotionJob` text→motion | `motion_greet_00.fbx` | retargeted onto the 28-bone rig |
| Offer | `SubmitHunyuanTo3DMotionJob` | `motion_offer_00.fbx` | retargeted |
| Clarify | `SubmitHunyuanTo3DMotionJob` | `motion_clarify_00.fbx` | retargeted |

Orchestration: `../cloud/run_pipeline.py` (one subcommand per stage; uploads to COS bucket
`nativelingo-ai3d-1418160727`, presigns, submits, polls, downloads). Signing probe and COS
round-trip probe live alongside it. **Credentials are read from outside the repo**
(`~/Developer/NativeLingo-survival/混元SecretKey.csv`) and never enter this tree.

Assembly: `../blender/assemble_gate_d_v06.py` (headless, `--factory-startup`). Imports the idle
FBX as the master 28-bone rig + LOD0 mesh, migrates the walk action, weight-transfers LOD1/LOD2
from LOD0 by nearest-vertex (KDTree), retargets the three gestures via COPY_ROTATION constraints
baked to fresh actions (Mixamo-modern 52-bone → Mixamo-legacy 28-bone mapping; fingers dropped),
normalizes to 1.78 m with feet at the origin, assigns the Art Bible base-color material, mounts
all five actions on NLA tracks, and exports the GLB. See `assemble_c1_report.json`.

## User-authored Mixamo action overlay

The same LOD0 mesh was exported to `../mixamo/chr_player_juvenile_tpose.fbx` and used to author
the eight FBX actions in `anime/`: `Standing Idle.fbx`, `Walking.fbx`, `Standard Run.fbx`,
`Pointing Gesture.fbx`, `Looking Around.fbx`, `Picking Up.fbx`, `Walking Turn 180.fbx`,
and `Jumping.fbx`.
`../blender/retarget_mixamo_actions.py` maps the 22 shared deform bones onto the target 28-bone
rig, evaluates local-basis, world-rest, and direction-plus-twist retargeting, and selects the
lower-error result
using per-frame world-space bone orientation after rest-axis calibration. The exported actions
select the lowest-error `pose_direction` result and are written
in-place to `game/assets/characters/chr_player_juvenile_mixamo.fbx`.

Runtime names include Idle, Walk, Run, Point, Observe, Gather, Turn 180, and Jump.
`Standing Idle.fbx` replaces the cloud-generated idle under the existing
`anim_chr_player_idle_neutral` contract. `PlayerController` chooses walk below the sprint
threshold, run above it, uses Point for grounded gestures, Gather for berry/scrap/water,
Observe for fixed facilities, and synchronizes Turn/Jump with movement and contact markers;
CharacterBody3D remains responsible for world movement.

## High-poly PBR bake (2026-08-21)

`../blender/bake_highpoly_pbr_v01.py` mirrors Mira's verified selected-to-active
pipeline. It keeps the v05 Hunyuan GLB immutable as the visual source and the
v06 ReduceFace-high GLB immutable as the LOD0 geometry target, Smart Projects a
2K UV atlas, then bakes:

- `baked_pbr_v01/chr_player_juvenile_base_color_2k.png`;
- `baked_pbr_v01/chr_player_juvenile_normal_2k.png` (OpenGL tangent space);
- `baked_pbr_v01/chr_player_juvenile_ao_2k.png`.

The measured target-to-high surface distance is 1.403 mm mean / 5.777 mm P99 /
12.638 mm max. The pass preserves all 5,648 vertices and 11,293 triangles. Its
per-polygon UV transfer contract is consumed by
`../blender/retarget_mixamo_actions.py`, which writes UV0 and the named PBR
material onto `game/assets/characters/chr_player_juvenile_mixamo.fbx` without
changing the 28-bone rig, weights, or action pipeline. `CharacterVisual` binds
the external Base Color, Normal, and AO maps to skinned LOD0 in Godot; the
current UV-less LOD1/2 placeholders retain a named flat fallback.

## Gate D status (`game/tests/test_character_asset.gd`)

```
CHARACTER_ASSET_EVIDENCE bones=28 lods=[1,1,1] materials=["mat_chr_player_juvenile_pbr", "mat_chr_player_juvenile_lod_fallback"] morphs=0
```

Passing: FBX loads · Skeleton3D · 28 bones ≤72 · AnimationPlayer · all runtime
actions present · locomotion loop modes · LOD0/LOD1/LOD2 groups · named
materials · LOD0 UV0/tangents · 2K Base Color/Normal/AO runtime bindings.

Failing (1): **LOD0 facial blend shapes ≥3 (blink/jaw/viseme)**. No ai3d action generates morph
targets, so this is a manual Blender hand-off — see the "Known gaps" section.

## Known gaps (manual hand-off)

1. **Facial blend shapes** on LOD0 — at least `blink`, `jaw`, `viseme` shape keys must be
   authored on the LOD0 mesh in Blender and re-exported. Until then
   `policy.runtime_export_allowed` in `ASSET_LOCK_MANIFEST.json` stays `false` and the 16th Gate
   D check stays red.
2. **Animation detail** — finger bones are absent, so hands stay rigid. The
   selected `pose_direction` retarget is covered by walk/directional regression
   tests; further gesture polish remains an animation hand-off rather than a
   material blocker.
3. **Crest / sail layers** — the art bible wants three rear-swept sail head crests; the cloud
   retopo preserved the single bifurcated v05 crest. Splitting it is a Gate A sculpt item that
   was deferred to keep the pipeline automated.

## Files in this tree (immutable once a follow-up v07 begins)

- `cloud_raw/` — raw cloud outputs (3 LOD GLBs + OBJ + preview images, 2 rig FBX, 3 motion FBX).
- `cloud_jobs.json` — append-only job log (action, job_id, status, output files, measures).
- `cloud_outputs_inspect.json` — per-file structural dump (armatures, meshes, actions).
- `assemble_c1_report.json` — what the assembly script emitted.
- `baked_pbr_v01/` — repeatable high-to-low PBR bake, UV transfer contract,
  editable Blend source, GLB review package, report, and four-view previews.
- `README.md` (this file).

The current animated runtime FBX lives at
`game/assets/characters/chr_player_juvenile_mixamo.fbx`; the three external 2K
runtime maps live beside it.
