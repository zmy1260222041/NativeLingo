# Godot Version Reference

- **Project line**: Godot 4.6
- **Pinned editor/runtime**: 4.6.3-stable
- **Language**: GDScript
- **Last verified**: 2026-08-10
- **Official archive**: https://godotengine.org/download/archive/4.6.3-stable/
- **Official documentation**: https://docs.godotengine.org/en/4.6/

Godot 4.6.3 is a maintenance release in the 4.6 stable line. Patch releases in
the same stable line are expected to remain project-compatible and are preferred
for stability and bug fixes. Do not open or resave the project with Godot 4.7+
without an explicit engine-upgrade decision.

## Verified macOS artifacts

- `Godot_v4.6.3-stable_macos.universal.zip`
- SHA-256: `30630f3e9b11e10b35c1f90ba8814185dcec43fae1a48345159be7552c64bfe8`
- `Godot_v4.6.3-stable_export_templates.tpz`
- SHA-256: `3fbe2c0e2dec9d537ab9ec97bcf8da91dcf23357fc51f67092dd068d839290a8`

## Renderer and physics

- Renderer: Compatibility for the prototype and broad desktop coverage; revisit
  Forward+ when the final toon-lighting art test establishes a need for it.
- Physics: Jolt Physics, the default for new Godot 4.6 projects.
- Target: 60 FPS / 16.6 ms frame budget.

See `breaking-changes.md`, `deprecated-apis.md`, and
`current-best-practices.md` before changing engine-facing systems.
