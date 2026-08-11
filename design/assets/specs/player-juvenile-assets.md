# Asset Specs — Character: Player Juvenile

> **Visual source**: `source_locked_v04/reference/figure_view_{0,1,2,3}.png`
> **Pipeline**: Rodin → clean Blender import → four-view sculpt → retopology → rig/animation → Godot
> **Art Bible**: `design/art/art-bible.md` §§1–4, 8–9
> **Status**: Gate A base imported; runtime export disabled

## Locked Character DNA

Original upright juvenile alien, alert and self-directed. Narrow ribcage, seed-pod pelvis, long lower
legs, broad three-digit hands, three-toed feet, embedded eyes with visible lids, and a small flexible
mouth. Exactly three unequal sail plates grow only from the rear/top of the skull and sweep backward.
The only wearable is a salvaged incomplete-loop sash with simple sole wraps.

Palette: warm gray-apricot `#BFA982`, Bark Plum `#5A3F58`, Dusk Indigo `#34335E`, restrained
Signal Orchid `#9A6ACB`, Dust Cream `#E7D2A3`, Hearth Amber `#F2A85B`.

Forbidden: tail, wings, lateral ears, muzzle, fangs, dog posture, giant black eyes, blue/cyan body,
superhero uniform, wrist device, transformation/hourglass symbol, copied franchise silhouette or pose.

## Production contract

| Field | Value |
|---|---|
| Concept authority | `art/source/characters/chr_player_juvenile/source_locked_v04/reference/figure_view_{0,1,2,3}.png` |
| Protected imported baseline | `art/source/characters/chr_player_juvenile/source_locked_v04/rodin_source/chr_player_juvenile_rodin_v04.blend` |
| First editable sculpt | `art/source/characters/chr_player_juvenile/source_locked_v04/sculpt/chr_player_juvenile_gate_a_v01.blend` |
| Current exchange mesh | `art/source/characters/chr_player_juvenile/source_locked_v04/rodin_processed/chr_player_juvenile_rodin_v04_normalized.glb` |
| Canonical standard | `design/art/character-modeling-standard.md` |
| Asset-specific stages | `art/source/characters/chr_player_juvenile/source_locked_v04/RODIN_PRODUCTION_PIPELINE.md` |
| Height | 1.78 m |
| Runtime axes | Y-up, front `-Z`, scale 1.0 |
| Origin | midpoint between grounded feet |
| LOD budgets | LOD0 ≤32k; LOD1 ≤16k; LOD2 ≤6k triangles |
| Materials | ≤3 named slots |
| Skeleton | ≤72 deform bones; ≤4 influences/vertex; remove weights `<0.02` |
| Runtime package | must not exist until Gate D passes |

## Current Rodin base

11,668 welded source vertices, 23,332 triangles, one closed connected component, zero non-manifold
edges and zero loose vertices. Rodin PBR is retained only for visual inspection; final materials are
authored from the Art Bible.

Gate A blockers: remove the invented tail; repair eye sockets, lids, three sail layers, three-digit
hands, three-toed feet, joint landmarks and bilateral consistency.

## Deliverables

1. `chr_player_juvenile_lod0`: animation-ready quad topology, ≤32k triangles.
2. `chr_player_juvenile_lod1`: shared skeleton/material order, ≤16k triangles, switch at 10 m.
3. `chr_player_juvenile_lod2`: blink/jaw only, ≤6k triangles, switch at 22 m.
4. `mat_chr_player_body`, `mat_chr_player_sail`, optional wear slot; body 2K, sail 1K.
5. `sk_chr_player_juvenile`: ≤72 deform bones with three digits per hand and three toes per foot.
6. Facial controls for lids, brows, jaw, mouth corners and required visemes.
7. Five 30 fps in-place actions: idle, walk, greet, offer and clarify.
8. Final `game/assets/characters/chr_player_juvenile.glb` only after Gate D.

## Validation gates

1. Four-view clay overlays match the approved concept and show no tail.
2. Three rear sails, three digits and three toes remain readable at 96 px.
3. Retopology contains continuous eye/mouth/joint loops and passes extreme-pose tests.
4. LOD/material/bone/influence budgets pass.
5. Godot imports the final GLB with three LOD groups, facial morphs and five exact animations.
6. Morning/night and fixed-camera captures preserve the Art Bible silhouette and materials.
