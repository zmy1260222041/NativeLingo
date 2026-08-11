# Character modeling standards audit — 2026-08-11

Verdict: `PASS WITH GATE A BLOCKERS PRESERVED`

## Scope

Reviewed the player, Mira and Rowan source locks, Rodin provenance, Blender import
scripts, Art Bible modeling rules, asset specs and references from the game README.

## Removed as obsolete or misleading

- Private-key Rodin Gen-2 submission script and its two unused preflight reports.
  They were never used to create the checked-in Mira/Rowan bases and could falsely
  present unverified endpoint fields as the canonical route.
- Eight JPEG proxy copies and their report fields. The path adapter failed for PNG
  and JPEG alike; the successful run read the locked RGB PNG bytes inside Blender.
- Duplicate player `views_contact.jpg`; the PNG evidence is canonical.
- Player runbook references that advertised the unused private-key route.
- Rejected/superseded NPC sheets and their old prompt/style-gate documents. Only
  the approved Mira v06 and Rowan v04 concept packages remain active.

## Corrected

- Added one cross-character standard covering source lock, Rodin base generation,
  sculpt/remesh, retopology, face/joint loops, materials, rigging, manual LOD and
  Godot wrapper integration.
- Reclassified procedural Godot geometry as runtime placeholder only, never a
  modeling or retopology source.
- Made registration reports repository-relative and added hashes for audit outputs.
- Changed Art Bible implementation order from obsolete silhouette blockout work to
  the actual Gate A repair state of the three imported Rodin bases.
- Expanded the asset manifest to include Mira and Rowan and kept runtime export blocked.

## Asset protection

- `ASSET_LOCK_MANIFEST.json` locks 23 approved/reference/baseline files by byte size
  and SHA-256.
- `.gitattributes` marks Blender, GLB and image assets as binary to prevent text merges.
- `verify_asset_locks.py` checks hashes and rejects credential/preflight artifacts.
- Future sculpt work must create versioned files and must not overwrite the locked
  Rodin import baselines.

## Remaining production blockers

All three Rodin meshes are valid closed bases but still fail Gate A for the
asset-specific shape issues recorded in their `GATE_A_REVIEW.md` files. No runtime
character GLB is approved by this audit.
