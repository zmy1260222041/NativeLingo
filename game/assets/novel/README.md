# Stranger 2D runtime art

Generated on 2026-09-11 with the built-in imagegen tool for FR-46. Original project art, not assets taken from the referenced games.

- `settlement_atlas.png`: 2 columns × 3 rows, plaza / food stall / store / workshop / porch / bedroom. Each tile is a 16:9 background. Runtime uses AtlasTexture; source image is unchanged.
- `cast_atlas.png`: transparent RGBA, 2172×724, Mira / Tavi / Ori / Vesh / Rowan. Runtime atlas boundaries are measured in `novel_screen.gd`. Mira references the repository's v06 turnaround; the other cast portraits adapt the existing roles to this 2D visual direction.
- Style: terracotta settlement, teal foliage, warm brass lamps, clean illustrated alien cast. Static full-body sprites, with the dialogue box overlapping the lower body in the main view.

Generated source files remain in the Codex generated_images directory; these copies are self-contained project assets. Original 3D character sources are not overwritten.
