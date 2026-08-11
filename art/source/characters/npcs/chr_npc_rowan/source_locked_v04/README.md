# Rowan v04 — Rodin source lock

Status: `RODIN_BASE_IMPORTED / GATE_A_SHAPE_REPAIR_REQUIRED`

- User-approved source SHA-256: `194dc52ffe29d6248b6548bb0b113f6c0293f82aac96448b2fa8c64e76cdc55b`.
- Canonical sheet: `reference/turnaround_source.png`.
- Rodin inputs: RGB `reference/figure_view_{0,1,2,3}.png`; RGBA versions are audit-only.
- Contract: `reference_manifest.json`, including the physical left/right face map.
- Deterministic crop evidence: `reference/registration_report.json`.
- Raw Rodin mesh: `rodin_raw/base_basic_pbr.glb`.
- Editable Blender base: `rodin_source/chr_npc_rowan_rodin_source_locked_v04.blend`.
- Normalized exchange mesh: `rodin_processed/chr_npc_rowan_rodin_source_locked_v04_normalized.glb`.
- Import evidence: `rodin_import_report.json` and `validation/rodin_*_clay.png`.

Generated through Blender Copilot's built-in Hyper3D free-trial route; no private
user key was entered. The job consumed 0.5 trial credit. The base has 11,668 welded
vertices / 23,332 triangles, one material, zero non-manifold edges and zero loose
vertices; it is normalized to 2.08 m with feet at `z=0`.

This is a sculpt source, not a runtime asset. `runtime_export_allowed=false` until
the blockers in `GATE_A_REVIEW.md` are repaired against all four locked views.
The files listed in `art/source/characters/ASSET_LOCK_MANIFEST.json` are immutable;
begin repair in `sculpt/chr_npc_rowan_gate_a_v01.blend`.
