# Player Juvenile — Rodin/Blender Validation

> Date: 2026-08-11
> Status: Gate A base imported; shape repair required

## Canonical evidence

| Check | Result |
|---|---|
| Concept views | `art/source/characters/chr_player_juvenile/source_locked_v04/reference/figure_view_{0,1,2,3}.png` |
| Raw Rodin delivery | `art/source/characters/chr_player_juvenile/source_locked_v04/rodin_raw/base_basic_pbr.glb` |
| Reproducible import | `art/source/characters/chr_player_juvenile/blender/import_render_rodin_v04.py` |
| Protected imported baseline | `art/source/characters/chr_player_juvenile/source_locked_v04/rodin_source/chr_player_juvenile_rodin_v04.blend` |
| Normalized exchange GLB | `art/source/characters/chr_player_juvenile/source_locked_v04/rodin_processed/chr_player_juvenile_rodin_v04_normalized.glb` |
| Machine report | `art/source/characters/chr_player_juvenile/source_locked_v04/rodin_import_report.json` |
| Four-view clay | `art/source/characters/chr_player_juvenile/source_locked_v04/rodin_raw/views_contact.png` |
| Runtime package | Absent until Gate D |

## Base-mesh checks

| Check | Result |
|---|---:|
| Source vertices after weld | 11,668 |
| Triangles | 23,332 |
| Connected components | 1 |
| Non-manifold edges | 0 |
| Loose vertices | 0 |
| Height | 1.78 m |
| Ground/origin | feet at `z=0`, horizontal center at origin |
| Material evidence | one Rodin PBR material, three embedded 512² maps |

The raw GLB contains coincident attribute-boundary vertices. The deterministic Blender import welds
them at `1e-6 m`, recalculates normals and saves the closed editable source. glTF may split render
vertices again at UV/normal discontinuities; the Blender source remains the topology authority.

## Gate A verdict

`FAIL / SHAPE_REPAIR_REQUIRED`.

The base is valid geometry and visually close to the concept, but Rodin generated a tail that is not
present in the design. Eye sockets, three sail layers, hands, toes, heels and bilateral consistency
also need a four-view sculpt pass. Runtime export stays disabled until the shape, retopology, rig,
animation, material and Godot gates all pass.

The imported baseline is immutable under `art/source/characters/ASSET_LOCK_MANIFEST.json`.
Shape repair begins in a versioned `sculpt/chr_player_juvenile_gate_a_v01.blend` copy.
