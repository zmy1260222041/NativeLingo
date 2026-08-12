# Tavi v06 — concept source lock

Status: `SOURCE_LOCKED_USER_APPROVED / REFERENCE_PREP_PENDING`

- User approval date: `2026-08-11`.
- Canonical sheet: `reference/turnaround_source.png`.
- Canonical SHA-256: `ff9b58cf3f0b6710a0e2a179d4ab435f7acafd02d28b3c6c2900242c89c4ebf5`.
- Visual contract: `reference_manifest.json`.
- Approval and pending technical work: `SOURCE_LOCK_REVIEW.md`.
- Generation provenance: `source_generation.prompt.md`.
- Stable character specification: `design/assets/specs/tavi-assets.md`.

The user selected this exact sheet as Tavi's only visual and modeling authority;
v02–v05 were discarded. Files protected by
`art/source/characters/ASSET_LOCK_MANIFEST.json` are immutable. Any design change
must create a new `source_locked_vXX` package.

This package is not yet a Rodin or runtime asset. Deterministic view splitting,
registration measurements and `target_height_m` must be completed before any 3D
submission. Those steps may derive data from the canonical sheet but may not edit it.
