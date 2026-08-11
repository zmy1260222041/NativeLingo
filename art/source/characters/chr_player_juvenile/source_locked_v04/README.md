# Player juvenile — Rodin source

Status: `RODIN_BASE_IMPORTED_GATE_A_PENDING`

This directory is the single source of truth for the Stranger player character. The approved
concept views remain the visual contract; Rodin supplies only the initial editable surface.

## Canonical files

- Concept views: `reference/figure_view_{0,1,2,3}.png`.
- Generation/import runbook: `RODIN_FROM_CONCEPT_RUNBOOK.md`.
- Production stages: `RODIN_PRODUCTION_PIPELINE.md`.
- Cross-character modeling rules: `design/art/character-modeling-standard.md`.
- Raw Rodin delivery: `rodin_raw/base_basic_pbr.glb` and `rodin_raw/preview.png`.
- Deterministic Blender builder: `../blender/import_render_rodin_v04.py`.
- Editable Blender source: `rodin_source/chr_player_juvenile_rodin_v04.blend`.
- Normalized exchange mesh: `rodin_processed/chr_player_juvenile_rodin_v04_normalized.glb`.
- Machine-readable evidence: `rodin_import_report.json`.
- Current review: `GATE_A_REVIEW.md` and `validation/`.

## Verified base

- 11,668 welded source vertices / 23,332 triangles.
- One closed connected component, zero non-manifold edges, zero loose vertices.
- 1.78 m tall, grounded at `z=0`, horizontally centered.
- One source PBR material with three embedded 512² maps.
- Raw source forward is Blender `-Y`; runtime conversion to Godot `-Z` happens only at export.
- `runtime_export_allowed=false` until every production gate passes.

## Current blockers

Rodin invented a tail from the waist/sash region and softened several view-dependent structures.
Before retopology, remove the tail and correct the eye sockets, three sail layers, hands, feet and
left/right consistency against all four concept views.

No player GLB belongs in `game/assets/characters/` until Gate D is complete.
Do not sculpt directly in the protected `rodin_source` baseline; begin with a
versioned `sculpt/chr_player_juvenile_gate_a_v01.blend` copy.
