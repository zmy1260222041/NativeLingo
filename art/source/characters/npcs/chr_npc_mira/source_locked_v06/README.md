# Mira v06 — Rodin source lock

Status: `REFERENCE_V03_REPAIRED / LEGACY_RODIN_BASE_INVALIDATED / HUNYUAN_CANDIDATE_V01_GENERATED`

## Hunyuan3D Pro candidate (v01, 2026-08-12)

Generated from the same locked four views via the verified ai3d direct-sign route
(`hunyuan_generate.py`, mirrors `chr_player_juvenile/source_locked_v05/HUNYUAN_FROM_CONCEPT_RUNBOOK.md`).
`hunyuan_generate.py` previously failed silently (`JobId=None`); its TC3 signing now
matches the working addon path exactly — credential Date is `YYYY-MM-DD`, the canonical
headers include `x-tc-action:<action lower>`, and the string-to-sign uses the UNIX
timestamp.

- Raw Tencent GLB: `hunyuan_raw/mira_hunyuan_mv_v01.glb` (≈32 MB, JobId 1479113105623433216).
- Editable Blender base: `hunyuan_source/chr_npc_mira_hunyuan_v06.blend`.
- Normalized exchange mesh: `hunyuan_processed/chr_npc_mira_hunyuan_v06_normalized.glb`.
- Import evidence + 贴好图 audit: `hunyuan_import_report.json` and
  `validation/hunyuan_mv_textured_hero.png`.

Mesh: 305,843 verts / 499,830 tris / 1 Principled-BSDF material with a baked
4096² texture on Base Color (`texture_20250901`), normalized to 1.72 m, feet at `z=0`,
2087 connected components / 108,488 non-manifold edges (dense AI base — expected, not a
manifold failure). Gate A clay views: `validation/hunyuan_mv_{ny,px,py,nx}_clay.png`.
`runtime_export_allowed=false` — Gate A silhouette/landmark review against the masks is
still required before retopology/rig/animation/LOD/Godot runtime replacement.

## Quadriflow LOD0 retopo candidate (v01, 2026-08-12)

Bulk quad retopology of the Hunyuan high-poly (`quadriflow_retopo_v01.py`). Per
`design/art/character-modeling-standard.md` §1.5, asset locks were verified before/after;
the verifier's 2 player-side failures (chr_player_juvenile v04 .blend, missing runtime
glb) are pre-existing/committed in `e7e748ff`, unrelated to Mira, deferred.

- Retopo source (read-only): `hunyuan_processed/chr_npc_mira_hunyuan_v06_normalized.glb`;
  cleanup welded 56,060 coincident verts → 249,871 verts, silhouette unchanged.
- LOD0 mesh: `retopo/chr_npc_mira_lod0_quadriflow_v01.blend` (+ `.glb`) — 10,814 faces,
  **100% quads**, 21,628 tri-equivalent, 6 non-manifold / 6 boundary edges (≈closed),
  253 valence-3 + 369 valence-5 poles, height 1.715 m.
- Clay: `validation/quadriflow_lod0_clay_front.png` (visually: coherent humanoid, all limbs
  separated, no defects). Report: `retopo/quadriflow_report.json`.

This is **bulk topology only** — Quadriflow field-aligned quads carry NO deformation edge
loops. Tri count (21.6k) sits just under the 24–30k NPC LOD0 budget on purpose, leaving
room for the manual loop pass. Remaining blocks before this is riggable: Gate A sculpt of
the high-poly → manual deformation loops (face/joints/3-finger knuckles/wedge feet) →
Shrinkwrap onto sculpted high-poly → Normal+AO bake → UV + repaint Base Color → Rigify rig.

- User-approved source SHA-256: `7e4e4769148dceea30f025706b55973f2666816d705899ed28136e240a0d545c`.
- Canonical sheet: `reference/turnaround_source.png`.
- Current Rodin inputs: RGB `reference/figure_view_{0,1,2,3}.png`;
  matching RGBA images and masks are audit-only.
- Contract: `reference_manifest.json`.
- Deterministic crop evidence: `reference/registration_report.json`.
- Ground-line repair evidence: `source_analysis/ground_line_repair_v03.json` and
  `validation/ground_line_repair_v03_pixel_audit.png`.
- Raw Rodin mesh: `rodin_raw/base_basic_pbr.glb`.
- Editable Blender base: `rodin_source/chr_npc_mira_rodin_source_locked_v06.blend`.
- Normalized exchange mesh: `rodin_processed/chr_npc_mira_rodin_source_locked_v06_normalized.glb`.
- Import evidence: `rodin_import_report.json` and `validation/rodin_*_clay.png`.

The stored Rodin base was generated through Blender Copilot's built-in Hyper3D
free-trial route; no private
user key was entered. The job consumed 0.5 trial credit. The base has 11,664 welded
vertices / 23,332 triangles, one material, zero non-manifold edges and zero loose
vertices; it is normalized to 1.72 m with feet at `z=0`.

That Rodin base used the superseded v01 registered images whose ground-line cleanup
deleted sole pixels. It remains immutable audit evidence but is invalid as a sculpt
baseline. Do not begin shape repair from it. Resubmit all four root `reference`
images, then restart Gate A. `runtime_export_allowed=false`.
