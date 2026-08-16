# Ori v06 — concept source lock

Status: `SOURCE_LOCKED_USER_APPROVED / REGISTERED_V03_REPAIRED / TARGET_HEIGHT_PENDING`

- User approval date: `2026-08-12`.
- Canonical sheet: `reference/turnaround_source.png`.
- Canonical SHA-256: `3b3d2eca868b989b00ca6d0d4ac414f1e2ee5e86df0596abc0fc34b1d97c42c6`.
- Visual contract: `reference_manifest.json`.
- Approval and registration review: `SOURCE_LOCK_REVIEW.md`.
- Current deterministic split evidence:
  `reference/registration_report.json`.
- Ground-line repair evidence: `source_analysis/ground_line_repair_v03.json` and
  `validation/ground_line_repair_v03_pixel_audit.png`.
- Legacy orthographic metrics remain audit-only:
  `reference/orthographic_registration_report.json`.
- Generation provenance: `source_generation.prompt.md`.

The user selected this exact sheet as Ori's only visual and modeling authority.
Ori v01–v05 and the intermediate v06 edit source were discarded. Files protected
by `art/source/characters/ASSET_LOCK_MANIFEST.json` are immutable. Any visual design
change must create a new `source_locked_vXX` package.

The RGB `reference/figure_view_*` files are the promoted v03 modeling inputs;
matching RGBA images and masks are audit evidence. `target_height_m` remains unset,
so Rodin submission and runtime export remain blocked until scale is decided.
