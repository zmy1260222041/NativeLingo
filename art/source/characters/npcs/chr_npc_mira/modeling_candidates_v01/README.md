# Mira modeling-only concept candidates

Status: `MODELING CANDIDATES / NOT SOURCE LOCKED / USER REVIEW REQUIRED`

The immutable design authority remains:

- `../source_locked_v06/reference/turnaround_source.png`
- SHA-256 `7e4e4769148dceea30f025706b55973f2666816d705899ed28136e240a0d545c`

Nothing in this folder replaces or edits that source. These images translate the
approved design into more explicit volume for image-to-3D reconstruction and rig
alignment. They may be promoted to a future `modeling_locked_v01` only after explicit
user approval. They must never be used to overwrite `source_locked_v06`.

## Variants

### `graphic_volume_v01/`

The first, more graphic matte-3D interpretation. It is preserved as a valid alternate
candidate because it retains the 2D color-block read while adding plate thickness and
joint depth.

### `soft_pbr_v02/`

The second, soft-PBR modeling interpretation requested after reviewing v01:

- polished 3D-painted production concept art;
- restrained stylized PBR material cues;
- soft-edged block-plane cartoon 3D;
- no thick black outline;
- recessed nonhuman shell eye sockets and a tapered lower head plane;
- clearer shoulder-plate, arm-root, pelvis-socket, knee and ankle volumes.

This is a controlled modeling-only exception to the Art Bible's 2D concept-rendering
prohibitions. It does not change the game render target, source-locked silhouette,
palette, component inventory, asymmetry, equipment or surface-marking contract.

### `sculptural_pbr_v03/`

The higher-realism modeling interpretation derived after reviewing five user-supplied
full-body turnaround references:

- **Soft-Studio Sculpted Stylized-PBR Turnaround** rendering identity;
- resolved continuous digital-sculpt curvature instead of soft block-plane cartoon 3D;
- real shell thickness, bevels, sockets, overlaps and joint insertions;
- material-specific roughness, specular lobes, subtle normal relief and low-frequency
  tonal variation;
- controlled body/shell grain, harness weave and pouch construction without adding new
  design markings;
- no inked exterior contour, cel bands, flat material blocks or uniformly matte clay.

The five reference images are preserved under `style_references/` for rendering-language
provenance only. Their anatomy, faces, garments, palettes, guide lines, foot baselines and
contact shadows are explicitly excluded. The locked v06 Mira remains the sole authority.

`style_analysis.md` records the shared visual rules and the exact changes from v02.
`raw/chr_npc_mira_a_pose_raw_v03_rejected_low_arms.png` and
`raw/chr_npc_mira_t_pose_raw_v03_rejected_far_arm.png` are retained as audit evidence;
neither rejected sheet may be submitted for modeling.

### `rigid_multiview_v04/`

The corrected, preferred modeling candidate after cross-view inconsistency review:

- one rigid two-layer seed-pod head shared by front, character-left, back and
  character-right;
- both profiles retain substantial head depth, a separately recessed lower shell and
  the continuous cream interface rim;
- back head lobes correspond to the side projections, while the central purple
  shoulder/back structure begins below the head;
- exactly one tool pouch on Mira's physical-left hip: visible in front, character-left
  and back, completely occluded in character-right;
- A/T head cores are deterministically identical view by view, so the two sheets differ
  in arm pose rather than head design.

`multiview_constraints.md` records the rigid projection contract. The dedicated
`validation/rigid_multiview_report.json` records head shared-axis compatibility, A/T head
core equality and the physical-left pouch visibility matrix.

### `rigid_multiview_v05/`

The current preferred modeling candidate. It inherits v04's rigid head, pose registration
and single physical-left pouch, then corrects the last character-right projection error:

- the visible harness segment runs only from the gold clasp upward/back over Mira's
  physical-right shoulder;
- the rejected clasp-to-near-hip descending segment is removed from both A and T right
  profiles and the uninterrupted tan abdominal armor is restored;
- the pouch remains fully occluded in character-right;
- the other six prepared views are byte-identical to v04, and v04/source-locked files are
  preserved unchanged.

The two image-generated inpaint sources are retained under `raw/` for provenance. Final
right profiles are deterministic local composites clipped to the v04 subject silhouette;
the generator outputs are not submitted directly.

## Deliverables per variant

- `chr_npc_mira_a_pose_turnaround.png` — line-free four-view contact sheet.
- `chr_npc_mira_t_pose_turnaround.png` — line-free four-view contact sheet.
- `a_pose/*.png` — four 1024 x 1024 Hunyuan-ready views.
- `t_pose/*.png` — four 1024 x 1024 rig-alignment views.
- `*/registration_report.json` — crop, scale, background and file-hash evidence.
- `validation/validation_report.json` — registration and integrity summary.
- `validation/front_overlay_reference.png` — diagnostic silhouette overlay.
- `validation/rigid_multiview_report.json` — v04 head/pouch consistency evidence.
- `validation/right_strap_projection_report.json` — v05 local edit scope and strap/pouch
  projection evidence.
- `prompt.md` — generation prompt and controlled-deviation record.

All prepared images use a mechanically normalized solid `#E6E6E3` background. They
contain no text, panel labels, grid, floor plane, cast/contact shadow or foot ground line.

## View and handedness contract

Order is always front / exact character-left / back / exact character-right.

- Front image-left is Mira's physical right.
- Front image-right is Mira's physical left.
- Character-left exposes the same near-side structures seen on front image-right.
- Character-right exposes the same near-side structures seen on front image-left.
- Exact profiles show only the near eye; the back is faceless.
- T-pose profiles show the near arm and three-digit hand end-on; the far arm is occluded.

## Locked component and marking inventory

The candidate must preserve all 21 principal structures declared by the source-lock
manifest: head shell, neck notch, three distinct shoulder plates, torso, pelvis, paired
upper arms/forearms/hands/upper legs/lower legs/split wedge feet, harness and pouch.
The amber support clasp remains an explicit equipment subpart.

There are exactly six oval body markings: one three-oval group on each outer upper arm,
arranged one above and two below. No other body region has oval markings. The harness
system has exactly two repair-stitch groups.

## Known limits

- These bitmap sheets cannot prove that a generated 3D mesh will be watertight.
- No Hunyuan, ReduceFace, rigging or cloud validation job was run for this delivery.
- The silhouette IoU in each validation report is diagnostic because the locked source
  and A-pose candidate use different arm poses and rendering modalities.
- v03 intentionally uses a 35–40-degree A-pose, so full-body bbox-normalized IoU is
  especially pose-sensitive and is not an approval gate; locked identity and non-pose
  regions still require human visual review.
- v04 corrects the reported bitmap multiview contradictions, but bitmap consistency still
  cannot prove that an image-to-3D service will reconstruct a watertight manifold mesh.
- `soft_pbr_v02/raw/chr_npc_mira_t_pose_raw_v02_rejected_contact.png` is preserved as
  audit evidence only; adjacent figures touched, so it must never be submitted to Hunyuan.
