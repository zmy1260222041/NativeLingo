# Mira ReduceFace High — local post-repair candidates

The immutable cloud output is `../reduceface_high_01.glb` with SHA-256
`9f1aa85b218680113e733aa8d2536b295b3e19cfdc7177ca142c5297b6aeffb8`.
Nothing in this directory modifies it.

## Promoted candidate: `minimal_topology_repair_v02`

This candidate preserves the cloud surface and performs only bounded local
topology edits:

| audit item | source ReduceFace GLB | promoted candidate, fresh re-import |
|---|---:|---:|
| triangles | 12,957 | 12,956 |
| vertices | 6,486 | 6,487 |
| boundary edges | 2 | 0 |
| edges shared by more than two faces | 2 | 0 |
| winding conflicts | 22 | 0 |
| degenerate triangles | 3 | 0 |
| moved vertices | — | 0 |
| bounds changed | — | no |

The repair retessellates zero-area triangles, removes one microscopic open flap
with area `6.612390279769897e-07 m²`, and splits one four-face edge into
coincident manifold edge fans. Three of the four orthographic clay renders are
pixel-identical to the immutable cloud output; the remaining profile changes
only 8 of 589,824 pixels (`0.001356%`).

Whole-character voxel/SDF reconstruction and any other global surface
resampling are prohibited for Hunyuan and ReduceFace post-processing. Those
artifacts were visually rejected and removed from this asset package.

## PBR bake and current Godot review package

`minimal_topology_repair_v02/textured_v01/` derives from the promoted geometry
without moving vertices or changing its 12,956 triangles. The repeatable
`bake_minimal_repair_pbr_v01.py` pass creates a 2K UV atlas and projects the
immutable Hunyuan source into:

- `chr_npc_mira_base_color_2k.png`;
- `chr_npc_mira_normal_2k.png` (OpenGL tangent space);
- `chr_npc_mira_ao_2k.png`.

The three maps are embedded in
`chr_npc_mira_a_pose_reduceface_high_textured_v01.glb` with a named Principled
PBR material. The identical GLB is integrated at
`game/assets/characters/chr_npc_mira.glb`; Godot 4.6 imports Base Color, Normal,
AO, UV0 and tangents successfully. This is a static A-Pose gameplay review
visual, not a rigged or animation-approved final character.

`surgical_prune_v01` remains only as negative evidence of the earlier component-
deletion approach and must not be used. The untextured
`minimal_topology_repair_v02` GLB remains the immutable geometry baseline for
the versioned texture pass above.
