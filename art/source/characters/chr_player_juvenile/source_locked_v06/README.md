# Player juvenile — v06 cloud-built runtime candidate

Status: `CLOUD_PIPELINE_COMPLETE / GATE_D_15_of_16 / BLENDSHAPES_PENDING_MANUAL`

The first player runtime GLB to reach `game/assets/characters/chr_player_juvenile.glb`. Built
end-to-end from the v05 Hunyuan base via Tencent ai3d cloud jobs + a headless Blender assembly,
with no manual modeling. Triangle budgets all met; 15 of 16 Gate D contract checks pass.

## Pipeline (all stages reproducible from this tree)

Input: `../source_locked_v05/hunyuan_processed/hunyuan_multiview_v3_1_normalized.glb`
(299 293 verts / 500 000 tris, unrigged, untextured — the v05 Hunyuan3D Pro base).

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

## Gate D status (`game/tests/test_character_asset.gd`)

```
CHARACTER_ASSET_EVIDENCE bones=28 lods=[1,1,1] materials=["mat_chr_player_juvenile"] morphs=0
```

Passing (15): GLB loads · Skeleton3D · 28 deform bones ≤72 · AnimationPlayer · all 5 animation
names present · idle + walk loop mode · LOD0/LOD1/LOD2 mesh groups (double-underscore substring)
· 1 named material with non-empty resource_name.

Failing (1): **LOD0 facial blend shapes ≥3 (blink/jaw/viseme)**. No ai3d action generates morph
targets, so this is a manual Blender hand-off — see the "Known gaps" section.

## Known gaps (manual hand-off)

1. **Facial blend shapes** on LOD0 — at least `blink`, `jaw`, `viseme` shape keys must be
   authored on the LOD0 mesh in Blender and re-exported. Until then
   `policy.runtime_export_allowed` in `ASSET_LOCK_MANIFEST.json` stays `false` and the 16th Gate
   D check stays red.
2. **Visual quality** — proportions, orientation, gesture retarget fidelity, and material
   flatness (no PBR texture yet; a single flat Art Bible color) need human review in the Godot
   editor. The gesture retarget copies rotations in world space across two Mixamo naming
   conventions; finger bones are absent so hands stay rigid.
3. **Crest / sail layers** — the art bible wants three rear-swept sail head crests; the cloud
   retopo preserved the single bifurcated v05 crest. Splitting it is a Gate A sculpt item that
   was deferred to keep the pipeline automated.

## Files in this tree (immutable once a follow-up v07 begins)

- `cloud_raw/` — raw cloud outputs (3 LOD GLBs + OBJ + preview images, 2 rig FBX, 3 motion FBX).
- `cloud_jobs.json` — append-only job log (action, job_id, status, output files, measures).
- `cloud_outputs_inspect.json` — per-file structural dump (armatures, meshes, actions).
- `assemble_c1_report.json` — what the assembly script emitted.
- `README.md` (this file).

The runtime GLB itself lives at `game/assets/characters/chr_player_juvenile.glb` (outside this
tree, under the Godot project) and is registered in `ASSET_LOCK_MANIFEST.json`.
