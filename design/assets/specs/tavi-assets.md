# Asset Specs — Character: Tavi

> **Asset ID**: ASSET-016
> **Visual authority**: `design/art/art-bible.md` v1.3, §§1–4, 8–9
> **Character source**: `art/source/characters/npcs/chr_npc_tavi/source_locked_v06/reference/turnaround_source.png`
> **Current lock**: `art/source/characters/npcs/chr_npc_tavi/source_locked_v06/reference_manifest.json`
> **Status**: Source locked / user approved / technical reference preparation pending / runtime export prohibited

## Rule hierarchy

This file is the stable Tavi character specification. Versioned `*.prompt.md` files
are self-contained image-tool execution records, not competing design authorities.

1. `design/art/art-bible.md` controls world shape language, color semantics,
   line/shadow treatment, detail density, originality and four-view gates.
2. This file controls Tavi's persistent character DNA, registered part inventory,
   handedness and approved character-local palette direction.
3. `chr_npc_tavi_turnaround_vXX.prompt.md` records only the complete reproducible
   prompt and that version's explicit deltas.
4. `chr_npc_tavi/source_locked_v06/` is the immutable shape source approved by the
   user on 2026-08-11. Any later shape change requires a new `source_locked_vXX`.

If a prompt conflicts with the Art Bible or this file, the prompt is wrong.

## Stable character DNA

Tavi is a capable living settlement repairer whose first read is one stout walking
seed pod plus one separate crescent tool. The personality is alert, practical and
slightly mischievous, never infantile, plush or pet-like.

- Proportion: about 3.25 heads tall; main pod about 1.55 head-widths wide.
- Connection: one uninterrupted head/torso pod; no neck, human shoulder line,
  rib cage, waist or visible pelvis.
- Crown: exactly five asymmetric folded husk lobes with one dominant front-middle
  lobe slightly offset toward physical-left.
- Arms: both grow from the mid-body walls. Physical-right forearm is about 22%
  broader than physical-left but remains organic.
- Hands and feet: exactly three digits per hand and three seed-wedge lobes per foot.
- Face: two compact upright rounded-seed eye islands with thick hooding upper lids,
  thinner lower lids, unequal round irises and vertical pupils. The mouth is one
  small off-centre seed-valve with a thin upper rim, fuller lower lobe, two corners
  and a narrow real oral aperture; it is not a painted crack.
- Tool: one separate Old-Alloy open-crescent repair clamp held only in the
  physical-right hand; it is neither flesh, prosthetic nor weapon.

## Locked structural direction (v06)

Exactly three shallow raised husk plates grow from the five crown roots:

1. `H1 Tool Gate` frames the physical-right work-arm opening and continues into
   the outer rear arc.
2. `H2 Long Wrap` crosses the upper front asymmetrically and becomes the middle
   rear arc.
3. `H3 Counter Wrap` forms the inner rear turn and returns to the lower front.

The three plates use different widths, tapered shell tips and purposeful angular
steps. They never cross or become straps, fabric, armor, painted stripes or
concentric rings. Together they form one broad open back swirl offset toward
physical-left. A single narrow inner-husk reveal sits on the lower front, also
offset toward physical-left; no round belly panel is allowed.

Body marking inventory is **one registered group**: two short shallow score marks on
the outer physical-right broad forearm. The front and exact physical-right profile
show the same pair under rotation; it must not multiply, migrate or mirror to the
physical-left arm. All other richness comes from modelable husk overlap, crown roots,
the work-arm opening, palm/ankle articulation and the tool.

## V06 facial structure

- Eye islands are rounded upright seed ovals, about 1.15 times taller than wide;
  they are rounder than Mira's almond eyes but not perfect circles or giant infant
  eyes. The ochre upper lid overlaps the top 15–20% and lowers slightly at the outer
  corner to keep Tavi focused rather than surprised.
- Each eye contains one Hearth-Amber round iris with a clear Inner-Husk sclera border
  and one vertical Silt-Ink pupil. Physical left/right retain a purposeful small size
  difference through the matching profile projection.
- The mouth has a thin upper lobe, fuller lower pad, two connected corners, a narrow
  Silt-Ink oral opening, two short cheek attachment folds and one hard shadow below
  the lower pad. No teeth or tongue appear in neutral.
- Profiles show only the near eye and near mouth corner with slight lip-rim depth;
  the back remains faceless. The structure must support blink, upper/lower lid,
  jaw/aperture and independent mouth-corner animation.

## Character-local palette

Percentages describe visible character/tool color area, excluding the background.

| Color | Hex | Area | Registered use |
|---|---:|---:|---|
| Weathered Ochre | `#B48745` | 53% | Pod core, limbs and five crown lobes |
| Charred Husk | `#68483A` | 15% | Three raised spiral husk plates and their local hard shadow faces |
| Old Alloy | `#A8B4BC` | 12% | Separate crescent clamp only |
| Inner Husk | `#C8B58A` | 8% | Narrow lower-front reveal and restrained palm/sole articulation |
| Patina Teal | `#3F6E65` | 6% | Three fixed under-husk windows only |
| Hearth Amber | `#F2A85B` | 3% | Irises and clamp hinge only |
| Silt Ink | `#17243B` | 3% | Ink, pupils and tool grip |

The three Patina-Teal windows are: physical-right arm opening, `C1–C2` crown-root
gap and `C4–C5` crown-root gap. They are projections of one fixed inventory and
must not multiply between views. Weathered Ochre is intentionally darker, grayer
and browner than Hearth Amber so the body does not inherit the HUD/shelter safety
semantic.

## Orthographic and handedness contract

Order is front / exact physical-left / back / exact physical-right.

- Front image-left = physical-right broad work arm and clamp.
- Front image-right = physical-left slim arm and the side toward which the narrow
  inner-husk reveal is offset.
- Exact physical-left shows the slim near arm; the far clamp may disappear only by
  real occlusion.
- Back image-right = physical-right broad work arm and rear clamp projection.
- Back image-left = physical-left slim arm; the open rear swirl is offset toward
  this side.
- Exact physical-right shows the broad near work arm, husk opening and clamp.
- Profiles share one outer depth envelope. Profiles show only the near eye; back
  shows no face.

## Hard-count inventory

- Primary parts: 22 — one pod core, five crown lobes, two upper arms, two forearms,
  two three-digit hands, two legs, two three-lobed feet, three spiral husk plates,
  one physical-right arm opening, one face system and one separate clamp.
- Body marking groups: 1 — exactly two short score marks on the outer
  physical-right broad forearm; no other body marks.
- Clamp: one crescent, one hinge, two large edge chips, two repair-stitch groups,
  exactly four broad plate seams and one wrapped grip.
- Front production density: 12–18 purposeful internal lines and 8–14 major
  connected color blocks with large quiet ochre surfaces between detail clusters.

## Production contract

| Field | Value |
|---|---|
| Locked concept | 1491 x 1055 lossless PNG, warm off-white background; SHA-256 `ff9b58cf3f0b6710a0e2a179d4ab435f7acafd02d28b3c6c2900242c89c4ebf5` |
| Final source package | `art/source/characters/npcs/chr_npc_tavi/source_locked_v06/` |
| Reference registration | Deterministic four-view split and measurement pending; this may not alter the locked sheet |
| Target height | unresolved; blocks Rodin submission until approved |
| LOD budgets | LOD0 24k–30k; LOD1 <=13k @ 9m; LOD2 <=5k @ 20m |
| Texture budget | 2K character maximum; Base Color sRGB; ORM/Normal linear |
| Material slots | <=3; body/eyes/husks share a primary atlas where practical |
| Skeleton | <=68 deform bones; <=4 influences/vertex; remove weights below 0.02 |
| Runtime | Y-up, faces -Z, feet-midpoint origin, scale 1.0 |

The three husk plates, arm opening and broad back swirl are real shallow geometry at
LOD0. LOD1 retains their principal overlap edges; LOD2 may bake only shallow inner
ridges that do not affect silhouette or the tool-arm opening. The clamp remains a
separate attachable mesh.

## Prohibited drift

No coral/red body, symmetric V chest plates, round cream belly, additional body
markings beyond the locked physical-right score pair, random spots, armor stack,
fabric wraps, robot body, visor, black-green technology,
wrist device, emblem, human chest/pelvis, blue body, lateral ears, canine muzzle,
copied franchise anatomy, gradients, AO, PBR concept rendering, soft shadow,
microtexture or view-specific surface redesign.
