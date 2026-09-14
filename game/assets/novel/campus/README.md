# Campus illustration assets

Six original campus backgrounds generated with the built-in imagegen tool on
2026-09-12 (local date), using the existing settlement atlas as a style reference.
Each is a separate 1672×941 RGB PNG; runtime preserves aspect ratio when covering
the stage. No source town asset was changed.

`class`, `study`, `club`, `dining`, `sports`, `home` map directly to campus locations.
Warm stone and brick, sage foliage, golden light, fine contours and painted material
detail follow the town's established illustrated direction. Campus content uses
human university spaces, not the town's alien setting.

Eight character sources are saved under `art/source/campus/illustrated_v01/`.
After explicit user approval, `extract_alpha.py` extracted genuine RGBA portraits,
reconstructed edge colors and removed magenta spill. All eight final portraits are
1024×1536; the audit found zero visible magenta pixels. Runtime preloads the final
textures with mipmaps, proportional layout and active-speaker tint.

Exact prompts and original generated-image paths:
`docs/reviews/campus_art_2026-09-12/generation.json`.
Alpha audit, rendered comparisons and playtest findings are in that review folder.
