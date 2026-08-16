# Rowan v04 — Rodin source lock

Status: `REFERENCE_V03_REPAIRED / LEGACY_RODIN_BASE_INVALIDATED / RESUBMISSION_REQUIRED`

- User-approved source SHA-256: `194dc52ffe29d6248b6548bb0b113f6c0293f82aac96448b2fa8c64e76cdc55b`.
- Canonical sheet: `reference/turnaround_source.png`.
- Current Rodin inputs: RGB `reference/figure_view_{0,1,2,3}.png`;
  matching RGBA images and masks are audit-only.
- Contract: `reference_manifest.json`, including the physical left/right face map.
- Deterministic crop evidence: `reference/registration_report.json`.
- Ground-line repair evidence: `source_analysis/ground_line_repair_v03.json` and
  `validation/ground_line_repair_v03_pixel_audit.png`.
- Raw Rodin mesh: `rodin_raw/base_basic_pbr.glb`.
- Editable Blender base: `rodin_source/chr_npc_rowan_rodin_source_locked_v04.blend`.
- Normalized exchange mesh: `rodin_processed/chr_npc_rowan_rodin_source_locked_v04_normalized.glb`.
- Import evidence: `rodin_import_report.json` and `validation/rodin_*_clay.png`.

The stored Rodin base was generated through Blender Copilot's built-in Hyper3D
free-trial route; no private
user key was entered. The job consumed 0.5 trial credit. The base has 11,668 welded
vertices / 23,332 triangles, one material, zero non-manifold edges and zero loose
vertices; it is normalized to 2.08 m with feet at `z=0`.

That Rodin base used the superseded v01 registered images whose ground-line cleanup
deleted sole pixels. It remains immutable audit evidence but is invalid as a sculpt
baseline. Do not begin shape repair from it. Resubmit all four root `reference`
images, then restart Gate A. `runtime_export_allowed=false`.
