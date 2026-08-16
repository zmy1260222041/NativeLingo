# Mira rigid-multiview modeling candidate v05 — right strap repair provenance

## Scope

- Parent candidate: `../rigid_multiview_v04/`.
- Sole design authority remains `../../source_locked_v06/reference/turnaround_source.png`.
- Change scope: realistic modeling images only; original concept art is intentionally
  unchanged.
- Status: `MODELING CANDIDATE / NOT SOURCE LOCKED`.

## Repair request

Preserve v04 exactly except for the crossbody strap projection in character-right.

Right-profile strap contract:

- This view exposes Mira's physical right side; the character faces screen-right.
- The pouch remains fully hidden because it belongs only to the far physical-left hip.
- The visible black ribbed strap is the upper segment from the gold chest clasp, rising
  upward and backward over the visible physical-right shoulder toward the back.
- Remove the rejected lower segment descending from the clasp across the tan abdomen
  toward a near-side hip; restore uninterrupted tan abdominal armor beneath it.
- Preserve strap width, parallel ribbing, restrained PBR sheen and the gold clasp.

Head contract:

- One deep asymmetric seed-pod rigid head with two nested coral/cream volumes.
- Upper crown shell: thick brow/crown overhang with substantial profile depth.
- Lower recessed shell: separately visible lower face/underside volume beneath the crown,
  with a continuous dust-cream interface rim and a real undercut.
- Both exact profiles must expose both layers and the lower recess.
- Back must show corresponding upper and lower coral/cream rear lobes; the central purple
  shoulder/back structure starts below the short neck and is not a head layer.

Pouch contract:

- Exactly one pouch, owned by Mira's physical left hip.
- Visible in front on image-right, in character-left as the near pouch, and in back on
  image-left.
- Completely occluded in exact character-right: no pouch, tools, stitches, opening or edge.
- Harness visibility follows its own crossbody path and is not removed with the pouch.

The final images use the inpaint results only as local torso sources registered to the v04
subject envelope. The rest of every right profile remains v04; the other six views are
byte-identical to v04. See `multiview_constraints.md` for the complete rigid projection
and handedness contract.

## Iteration record

1. The first A repair corrected head depth/layers but accidentally removed the pouch from
   character-left and back; retained as `raw/*rejected_missing_left_pouch.png`.
2. Accepted A repair restored the single physical-left pouch to character-left and back,
   kept character-right pouch-free, and moved the purple back structure below the head.
3. T repair inherited the same two-layer head and pouch visibility while retaining the
   strict T arms and profile far-arm occlusion.
4. Mechanical preparation normalized actual keyed subject height to 900px, registered
   left/right profile depth symmetrically, removed studio-shadow residue and set the
   background to solid `#E6E6E3`.
5. Accepted A heads became the deterministic cross-pose head anchor. Each T head core is
   pixel-identical to the corresponding A view; the short neck/shoulder junction uses a
   narrow soft transition so only arm pose differs across A/T.
6. v05 generated isolated A/T right-profile corrections, mechanically registered each
   source to v04, clipped the edit to the existing subject silhouette, restored the pose
   authority arm/hand where required, and rebuilt both contact sheets.
7. Final-layer correction: the first local composite restored v04 head/arm pixels after
   the generated strap, which interrupted the band over the shoulder. The compositor now
   places the complete generated upper strap last, as one continuous layer from rear
   shoulder across the shoulder top to the gold clasp. A/T share the same canonical band
   mask, preventing both interruption and a cross-pose seam.

## Negative constraints

No concept-art edit, redesign, humanization, third head layer, flat single-layer side head,
contradictory back lobes, purple shoulder plate used as head, paired pouch, right-profile
pouch fragment, mirrored asymmetry, changed component count, changed markings, 3/4 view,
floor, foot line, contact/cast shadow, guide, text or watermark.
