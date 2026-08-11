# Rowan Gate A review

Verdict: `FAIL / SHAPE_REPAIR_REQUIRED`

## Verified technical state

- 11,668 welded vertices / 23,332 triangles.
- One closed mesh, zero non-manifold edges, zero loose vertices.
- 2.08 m tall, feet grounded at `z=0`, `runtime_export_allowed=false`.

## Shape blockers

1. Rebuild the lower body as the locked open-loop plate. Rodin incorrectly filled
   the opening and replaced it with a solid bulbous pelvis; this is the largest error.
2. Recover the two amber eye windows, vertical pupils and shallow mouth; the current
   wedge has almost no readable face.
3. Preserve physical-left wide / physical-right narrow face construction in front
   and both profiles rather than a generic wedge.
4. Rebuild each palm with exactly three digits; the generated two-prong claws fail.
5. Sharpen elbow, knee and ankle landmarks and remove the sawtooth surface artifacts
   running down the long limbs.
6. Restore the suspended upper plate and lower loop as separate designed structures,
   while preserving the good long-limb proportions and negative space.

Retopology, rigging, LOD and runtime export remain blocked until four-view overlays
and the 0.90 front-mask IoU gate pass.
