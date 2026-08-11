# Character source assets

This directory contains the protected character-modeling sources for Stranger.

## Authority order

1. `ASSET_LOCK_MANIFEST.json` defines the immutable, user-approved inputs and the
   imported Rodin baselines.
2. `design/art/character-modeling-standard.md` defines the cross-character
   production and validation rules.
3. Each `source_locked_vXX/README.md`, reference manifest and `GATE_A_REVIEW.md`
   defines asset-specific proportions, asymmetry and current blockers.
4. `design/art/art-bible.md` controls visual language, palette and performance.

The procedural geometry currently visible in the Godot prototype is a temporary
runtime placeholder. It is not a modeling source and must never be converted,
retopologized or promoted into a character asset.

## Protection rules

- Never overwrite a file listed in `ASSET_LOCK_MANIFEST.json`. Create a new
  `source_locked_vXX` or a versioned sculpt file instead.
- Keep Rodin raw deliveries and clean imported baselines unchanged. Gate A sculpt
  work begins in `sculpt/<asset_id>_gate_a_v01.blend`.
- Never place API keys, trial keys, subscription keys or signed download URLs in
  this tree.
- Run `python3 art/source/characters/verify_asset_locks.py` before and after any
  modeling session and before a Git commit.
- Runtime GLBs under `game/assets/characters/` remain prohibited until Gate D.
