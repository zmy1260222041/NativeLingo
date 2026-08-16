# Mira head multiview conflict report

Status: `SOURCE CORRECTION CANDIDATE / NOT SOURCE LOCKED`

## Problem class

The current `source_locked_v06` head cannot be interpreted as one unambiguous rigid
two-layer shell across the four orthographic views. This is a template contradiction,
not a material or rendering problem, and it propagates into every image-to-3D derivative.

## Normalized axis contract

- front and back: width = X, height = Z;
- character-left and character-right: depth = Y, height = Z;
- front image-left is Mira's physical right;
- back image-right is Mira's physical right;
- character-left faces image-left and exposes the physical-left shell;
- character-right faces image-right and exposes the physical-right shell.

## Observed source measurements

Measurements use the coral/cream head-material region in the registered 1024-square
views. They are diagnostic because the structural error is primarily part correspondence,
not total bounding-box size.

| View | Projected head span | Head height | Observation |
| --- | ---: | ---: | --- |
| front | X = 258 px | Z = 102 px | two-level frontal shell read is clear |
| character-left | Y = 201 px | Z = 107 px | lower/rear layer collapses to a thin sliver |
| back | X = 253 px* | — | central/lateral layers and unequal rear lobes are not explained by the profiles |
| character-right | Y = 205 px | Z = 107 px | lower/rear layer again collapses; physical-right lobe length is not registered |

`*` The back head is interleaved with the plum nape/neck stack, so a single material bbox
cannot represent its Z height reliably.

The left/right total depth differs by only about 2%, so simply scaling the profile wider
will not solve the problem. The contradiction is that the visible layer count, thickness,
rear termination and asymmetric lobe registration change between views.

## Part-correspondence conflicts

1. The front establishes an upper broad crown/brow shell and a lower face/undershell as
   two solid stacked volumes.
2. Both profiles flatten those volumes into one thin coral cap plus a small plum wedge;
   the lower shell has no stable underside or rear depth.
3. The back introduces a layered central nape construction plus unequal coral lateral
   lobes. Those lobes do not terminate at corresponding positions in the two profiles.
4. The intentional asymmetry is not handed: the longer back lobe is not carried into the
   physical-right profile and the shorter lobe is not carried into the physical-left.
5. Because no top view exists, a 3D generator is free to invent the missing transition,
   producing inconsistent heads and unstable reduction topology.

## Canonical policy

Policy: **`corrected_templates_required`**.

- The locked front is canonical for facial identity, X width, central crown peak, eye and
  mouth placement, frontal double-layer read and palette.
- The locked back is canonical only for the existence and handedness of the asymmetry:
  Mira's physical-right rear lobe is intentionally longer/more projecting; physical-left
  is shorter. Its exact contradictory outline is not canonical.
- Both locked profiles are noncanonical for head depth and layer visibility. They must be
  redrawn so each shows the same two solid layers and the correct near-side rear-lobe length.
- Everything below the neck notch remains source-locked and must not be redesigned.
- No model or modeling turnaround should claim final head fit until a corrected four-view
  2D template passes the correspondence gate.

## Corrected rigid-shell contract

The corrected head is one asymmetric two-layer seed-pod assembly:

1. **Upper crown/brow shell:** broad coral crown with the locked central peak, real dome
   thickness and a swept rear lobe. It is never a paper-thin plate.
2. **Lower face/nape shell:** the locked coral face and cream lower rim continue backward
   into a substantial bark-plum nape shell beneath the crown. The boundary is continuous
   through front, both profiles and back.

The physical-right rear lobe projects about 8% farther than the physical-left lobe. That
same difference must appear on back image-right, at the rear of the character-right
profile, and nowhere else. The front remains only subtly asymmetric because most of the
difference lies behind the widest frontal plane.

## Acceptance gate

- exactly the same two head layers are readable in all four views;
- no layer exists only in the back view;
- cream boundary and crown/nape overlap trace continuously across views;
- physical-right rear lobe is longer in both its back and profile projections;
- physical-left rear lobe is shorter in both projections;
- profile head reads as a solid pod, not a thin slab;
- eyes/mouth exist only in front and correct near-side profile;
- all below-neck shapes, parts, colors and registrations remain unchanged;
- no floor, foot line, guide, grid, text, cast/contact shadow or watermark.

