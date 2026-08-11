# Gate A review — Hunyuan3D Pro v3.1 multi-view base

Verdict: `CONDITIONAL_PASS / STRONGER_BASE_THAN_RODIN_V04 / SCULPT_REQUIRED`

## Source

- Candidate: `hunyuan_raw/hunyuan_multiview_v3_1.glb` — Tencent Hunyuan3D Pro, `Model=3.1`,
  inputs front + left + back + right (`MultiViewImages`).
- Four-view contract: `../source_locked_v04/reference/figure_view_{0,1,2,3}.png`.
- Editable base: `hunyuan_source/hunyuan_multiview_v3_1.blend`.
- Import evidence: `hunyuan_import_report.json`.
- Clay evidence: `validation/hunyuan_mv_{ny,px,py,nx}_clay.png`.
- Fair A/B evidence: `GATE_A_COMPARE.json`.

## Verified technical state

| Check | Result |
|---|---:|
| Height | 1.78 m |
| Source vertices | 299,156 |
| Triangles | 500,000 |
| Non-manifold edges | 95,466 (AI mesh; retopo cleans) |
| Connected components | 2,227 (floaters; removed at retopo) |
| PBR material | 1 slot, 4096² texture |
| Runtime export | disabled |

## Gate A silhouette IoU — fair same-method A/B vs Rodin v04

Method: absolute-distance silhouette, 1024 canvas, brute-force orientation match
(`blender/gate_a_compare_v04_v05.py`). Both candidates' clay views are run through one pipeline, so
the two means are directly comparable.

| View | Hunyuan v05 | Rodin v04 | Δ |
|---|---:|---:|---:|
| front | 0.778 | 0.707 | +0.071 |
| left | 0.739 | 0.632 | +0.107 |
| back | 0.638 | 0.537 | +0.101 |
| right | 0.321 | 0.311 | +0.010 |
| **mean** | **0.619** | **0.547** | **+0.072** |

Hunyuan v05 leads on every view. Rodin's previously-recorded ~0.72 mean used an earlier directional
threshold that does not separate a light model from a dark background; the table above is the only
comparable pair and is the authoritative A/B.

## Shape status (visual, vs concept)

- ✅ **No tail** — Rodin v04's fatal hallucination is gone.
- ✅ Three toes per foot, almond slit-pupil eyes, flat face (no muzzle), waist belt — all present.
- ✅ Slender ~3:1 humanoid proportions match the contract.
- ⚠️ Head crest simplified to a single bifurcated purple crest; the art bible requires three
  rear-swept sail layers — must be separated during Gate A sculpt.
- ⚠️ Skin reads paler than the concept's warm tan — a Stage 3 repaint, not a geometric blocker.
- ⚠️ Right-view IoU is low (~0.32); this is shared with Rodin (~0.31), so it is more likely a
  concept-view / methodology artifact than a Hunyuan-specific defect — confirm during sculpt.

## Remaining before retopology

1. Separate the single crest into the three rear-swept sail layers, validated in every view.
2. Remove floaters / degenerate faces so the base is one closed surface before quad retopo.
3. Re-run the four-view silhouette review after sculpt; never retopologize directly on the raw
   500k AI mesh.
