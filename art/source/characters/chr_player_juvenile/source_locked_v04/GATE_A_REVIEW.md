# Gate A review — Rodin anatomy base

Verdict: `FAIL / SHAPE_REPAIR_REQUIRED`

## Source

- Four-view contract: `reference/figure_view_{0,1,2,3}.png`.
- Editable base: `rodin_source/chr_player_juvenile_rodin_v04.blend`.
- Import evidence: `rodin_import_report.json`.
- Clay/PBR evidence: `validation/`.

## Verified technical state

| Check | Result |
|---|---:|
| Height | 1.78 m |
| Source vertices | 11,668 |
| Triangles | 23,332 |
| Connected components | 1 |
| Non-manifold edges | 0 |
| Loose vertices | 0 |
| Embedded texture maps | 3 × 512² |
| Runtime export | disabled |

## Shape blockers

1. Remove the generated tail; it is absent from the concept and violates the character contract.
2. Refine the embedded eye sockets, lids and forehead-to-muzzle wedge.
3. Separate and fit all three rear-swept sail layers in every view.
4. Correct shoulder, elbow, knee, calf and heel landmarks.
5. Make three digits per hand and three toes per foot readable at 96 px.
6. Resolve left/right asymmetry without flattening the intentional silhouette asymmetry.

Retopology, rigging, animation, LOD generation and runtime export remain blocked until these items
pass a four-view overlay review.
