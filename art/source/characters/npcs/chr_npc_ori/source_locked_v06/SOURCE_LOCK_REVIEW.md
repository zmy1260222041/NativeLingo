# Ori v06 — source-lock approval

Status: `SOURCE_LOCKED_USER_APPROVED / REGISTRATION_PASS / TARGET_HEIGHT_PENDING`

## Approval

The user explicitly approved Ori v06 and directed that all other Ori versions be
cleaned on 2026-08-12. The canonical source is
`reference/turnaround_source.png` with SHA-256
`3b3d2eca868b989b00ca6d0d4ac414f1e2ee5e86df0596abc0fc34b1d97c42c6`.

## Locked visual facts

- One large continuous blue crescent arches over the full character.
- The head is suspended from the short blue segmented connector at the crown.
- In both profiles, the narrow green neck bridge remains continuous from crescent
  to torso but is visibly separated from the head by Dust-Cream background.
- Front and back figures are the exact user-approved source panels and were not
  repainted during the profile correction.
- Four horizontally aligned eyes, long jointed limbs, three digits per hand and
  broad three-lobed feet are immutable.
- View order is front / character-left / back / character-right.

## Registration evidence

- All four views use shared scale `0.9715370018975332` on 512×1024 canvases.
- All four ground points resolve to y=952; baseline drift is 0 px.
- Front/back registered heights are 874/875 px; difference is 1 px.
- Bounding-box centers remain within the 12 px centerline tolerance.
- The project registrar generated RGB inputs, RGBA audits, masks and the contact
  sheet without repainting the canonical source.
- The generic orthographic skill helper could not run because OpenCV was absent;
  equivalent metrics were derived from the deterministic project masks with the
  bundled Pillow/NumPy runtime and recorded separately.

## Remaining technical gate

`target_height_m` is intentionally null. Set physical scale before Rodin submission.
`runtime_export_allowed=false`; source lock does not authorize a runtime asset.
Any visual correction requires a new version and must never overwrite v06.
