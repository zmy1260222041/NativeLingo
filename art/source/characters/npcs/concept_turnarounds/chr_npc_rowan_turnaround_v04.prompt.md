# Rowan turnaround v04 face-asymmetry correction

## Mode

- Skills: `orthographic-registration` + built-in `imagegen`
- Use case: `precise-object-edit`
- Edit target: `chr_npc_rowan_turnaround_v03.png`
- Intent: correct eyes, pupils, mouth and internal side-face registration only
- Art Bible: `design/art/art-bible.md` v0.9

## Locked coordinate map

- Figures are ordered front, exact character-left, back, exact character-right.
- In the front figure, image-left is Rowan's physical right/narrow side.
- In the front figure, image-right is Rowan's physical left/wide side.
- Exact character-left therefore exposes the wide facial side.
- Exact character-right therefore exposes the narrow facial side.
- The left/right outer Y/Z depth envelopes may remain near-mirrored; the visible
  face panels, eye sizes, seams and mouth lengths may not be mirror duplicates.

## Face edit

- Front narrow-side eye is smaller; front wide-side eye is larger.
- Every visible Hearth-Amber eye contains one solid dark vertical teardrop/oval
  pupil with a clear amber border and a shared calm forward gaze.
- Exact character-left has the larger near eye, broader face plane, farther-back
  panel seam and longer mouth segment.
- Exact character-right has the smaller near eye, narrower face plane, closer seam
  and shorter mouth segment.
- The mouth is a closed, shallow, asymmetric two-segment Bark-Plum/Silt-Ink line:
  longer toward the wide side, shorter toward the narrow side.
- Back has no eyes, pupils or mouth. No nose, black triangular mouth, open hole,
  beak, lips, teeth or smiley curve.

## Preserved invariants

Preserve the v03 body, pose, proportions, outer head wedge, plate map, zero-marking
surface inventory, Dusk-Indigo/Hearth-Amber/Dust-Cream palette, continuous solid
lines, hard color blocks, single cel-shadow tier, background, baseline and layout.

## Output provenance

- Generated source: `exec-7afe7f57-c78f-4c33-8c69-60cbc999519e.png`.
- Workspace candidate: `chr_npc_rowan_turnaround_v04.png`, 1491×1055.
- Workspace SHA-256: `194dc52ffe29d6248b6548bb0b113f6c0293f82aac96448b2fa8c64e76cdc55b`.
