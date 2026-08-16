# Mira modeling lock — A-Pose only, v01

This is a user-approved, modeling-specific A-Pose lock. It does **not** replace or
modify the original 2D `source_locked_v06` package, and it does **not** lock a
T-Pose.

- Source authority: `raw/chr_npc_mira_a_pose_user_approved.png`
- View order: front, character-left, back, character-right
- Modeling input: `hunyuan_input/chr_npc_mira_a_pose_{front,character_left,back,character_right}.png`
- Processing: external white letterbox crop plus mechanical background key/canvas
  registration only; no redraw, inpaint, mirroring, or structural edit.
- Background: flat `#E6E6E3`; no text, floor, foot baseline, or cast shadow.
- T-Pose: `UNLOCKED_NOT_INCLUDED`.

The approved source establishes that the ankle rings, two-layer head, harness route,
and single physical-left pouch are consistent between all four orthographic views.
`hunyuan_submission/` records a cloud generation as a downstream, non-locked result.

## Hunyuan post-processing policy

The immutable Hunyuan GLB remains the visual/bake authority. Whole-character
voxel/SDF reconstruction and other global surface resampling are forbidden as
Hunyuan or ReduceFace post-processing because they erase the approved layered
forms and negative spaces.

The only promoted ReduceFace topology repair is the local, shape-preserving
`hunyuan_submission/reduceface_high/post_repair_candidates/minimal_topology_repair_v02/`
candidate. It moves no vertices, changes no bounds, removes one microscopic flap,
retessellates zero-area triangles, and splits one over-subscribed edge. The
geometry baseline remains immutable; its versioned `textured_v01` derivative
adds only UV, normals, tangents and Hunyuan-projected Base Color/Normal/AO. That
derivative is integrated in Godot as a static A-Pose review visual, while rigging
and animation remain unapproved.
