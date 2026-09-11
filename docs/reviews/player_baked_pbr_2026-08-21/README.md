# Player high-poly PBR bake review — 2026-08-21

## Outcome

PASS for the requested material scope. The player now uses the same production
pattern as Mira: immutable Hunyuan high-poly visual source → selected-to-active
Base Color / OpenGL Normal / AO bake → UV transfer to the animated runtime
mesh → explicit Godot `StandardMaterial3D` binding.

## Bake evidence

| Check | Result |
|---|---:|
| Resolution | 2048 × 2048 |
| LOD0 vertices | 5,648 before / 5,648 after |
| LOD0 triangles | 11,293 before / 11,293 after |
| UV loops | 33,879 |
| High/low mean distance | 1.403 mm |
| High/low P99 distance | 5.777 mm |
| High/low max distance | 12.638 mm |
| Normal convention | OpenGL tangent space (+Y) |

Machine-readable details and source hashes are in
`art/source/characters/chr_player_juvenile/source_locked_v06/baked_pbr_v01/bake_report.json`.

## Runtime evidence

Blender re-import of the final FBX confirms 28 bones, 5,648 vertices, 11,293
faces, UV0 with 33,879 loops, the `mat_chr_player_juvenile_pbr` material, and
all eight authored Mixamo actions.

Godot 4.6.3 imports the asset and passes the new LOD0 checks for UV0, tangents,
material name, Base Color, tangent-space Normal, and AO. The pre-existing
facial-morph gate remains the only `test_character_asset.gd` failure
(`blink/jaw/viseme`, morph count 0); it is independent of this texture pass.

Regression results:

- `test_walk_fix.gd`: PASS;
- `test_directional_locomotion.gd`: PASS;
- `MainEnvIntegration.tscn`: PASS;
- `test_character_asset.gd`: new PBR assertions PASS; known morph assertion FAIL.

The four `runtime_player_*.jpg` files are actual Godot runtime captures under
scene lighting. They show the complete front, character-left, back, and
character-right views with no visible UV flip, missing projection, or major
bake artifact.

## Reproduce

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python art/source/characters/chr_player_juvenile/blender/bake_highpoly_pbr_v01.py

/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python art/source/characters/chr_player_juvenile/blender/retarget_mixamo_actions.py

/Applications/Godot-4.6.app/Contents/MacOS/Godot --headless --editor \
  --path game --quit
```
