# Technical Preferences — Stranger

## Decisions

- Use Godot 4.6.3-stable with GDScript.
- Build the vertical slice as a standalone project in `game/`.
- Prefer data-driven Resources and small, composable nodes over deep scene
  inheritance.
- Keep survival simulation deterministic and testable without rendering.
- Treat speech recognition as an optional local adapter. Never gate survival
  progress on pronunciation accuracy or service availability.
- Use original procedural placeholder art until licensed assets are audited.

## Constraints

- 60 FPS desktop target on Apple Silicon and mainstream Windows hardware.
- No network requirement for normal play.
- No multiplayer, seamless open world, base-building grind, or combat loot
  progression in the vertical slice.
- No copied characters, silhouettes, names, sounds, or iconography from the
  visual references.

## Allowed dependencies

- Godot built-in modules and GDScript standard APIs.
- A local speech service communicating over loopback HTTP/WebSocket, once its
  protocol is documented and failure path is tested.

## Forbidden patterns

- Gameplay state stored only in scene-node paths.
- Hard-coded keyboard scancodes instead of named InputMap actions.
- Language failure reducing health, inventory, relationships, or quest state.
- Mandatory online APIs for core gameplay.
