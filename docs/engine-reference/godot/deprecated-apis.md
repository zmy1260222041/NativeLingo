# Godot 4.6 Deprecated API Policy

Last verified: 2026-08-10.

- Treat editor warnings about deprecated APIs as build warnings to resolve,
  not as acceptable background noise.
- Prefer `CharacterBody3D` and its velocity/movement workflow for the player.
- Use named InputMap actions rather than direct physical-key polling.
- Use `FileAccess` and JSON-safe dictionaries for save data.
- Do not add APIs from `latest` documentation unless they are also present in
  the versioned Godot 4.6 documentation.

Run the headless smoke checks with the pinned editor after engine-facing code
changes; parser warnings and errors must be reviewed before handoff.
