# Godot 4.6 Current Practices

Last verified: 2026-08-10 against the versioned Godot 4.6 documentation.

- Use `CharacterBody3D` for script-controlled characters and call
  `move_and_slide()` from `_physics_process()`.
- Define controls in InputMap and expose matching keyboard/mouse and gamepad
  bindings.
- Keep persistent cross-scene state in a small autoload and serialize only
  plain data, not node references.
- Give controller users an explicit initial UI focus and preserve focus while
  navigating menus.
- Test gameplay logic headlessly and keep rendering-dependent smoke tests
  separate.
- Install export templates matching the exact editor patch version.
- Keep save formats versioned so later age chapters can migrate old saves.

For the vertical slice, core play must remain available without speech input:
the interaction wheel provides a physical/gesture confirmation and free retry.
