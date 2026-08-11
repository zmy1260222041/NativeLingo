# Mira turnaround v06 surface-registration correction

## Mode

- Tool: built-in image generation
- Use case: `precise-object-edit`
- Edit lineage: `chr_npc_mira_turnaround_v05.png` → intermediate registration attempt → final v06 cleanup
- Intent: enforce one shared surface-marking inventory across four views; no redesign
- Art Bible: `design/art/art-bible.md` v0.7

## Final locked marking inventory

| Side | Anatomical region | Count | Arrangement | Required visibility |
|---|---|---:|---|---|
| Left | Outer upper arm | 3 | one oval above, two below | front 3; left 3; back 3; right hidden |
| Right | Outer upper arm | 3 | one oval above, two below | front 3; left hidden; back 3; right 3 |

Total anatomical marking inventory: **exactly six spots**. Head, shoulders,
forearms, torso, hips, legs, feet and equipment contain no oval spots.

## Correction sequence

1. The first edit attempted head and upper-arm maps together. Upper-arm registration
   passed, but the front head sides differed and the rear projection omitted the
   head marks, so that intermediate was rejected.
2. The final edit removed every head spot in all four views while preserving the
   already-correct three-per-upper-arm map. Occluded marks disappear; no view may
   invent a replacement.

## Preserved invariants

Preserve the four-view order and registration, silhouette, proportions, pose,
nonhuman anatomy, clean flat color blocks, continuous structural lines, one hard
cel-shadow tier, face/mouth, shoulder construction, hands, feet, harness, clasp,
pouch and ground line.

## Avoid

No spots outside the six-item inventory, no count changes, mirrored layout errors,
replacement markings, dashed body lines, texture noise, gradients, AO, PBR, text,
labels, logo, watermark, extra figure, perspective or cropped feet.

## Output provenance

- Rejected intermediate: `exec-bbc94a92-e014-4082-9878-5e8734459e5a.png`.
- Generated final source: `exec-71cdf931-e589-4665-be79-31e5ef9a6c9d.png`.
- Workspace candidate: `chr_npc_mira_turnaround_v06.png`, 1491×1055.
- Workspace SHA-256: `7e4e4769148dceea30f025706b55973f2666816d705899ed28136e240a0d545c`.
