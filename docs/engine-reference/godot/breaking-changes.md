# Godot 4.6 Breaking-Change Notes

Last verified: 2026-08-10 against the official Godot 4.6 documentation.

This is a new 4.6 project, so no migration is required at project creation.
Future upgrades must review the official 4.6 migration guide before scenes or
resources are resaved.

Project-sensitive areas to recheck during an upgrade:

- renderer defaults and compatibility behavior;
- physics backend and collision behavior;
- GDScript parser and typed-array changes;
- input event serialization;
- resource and scene file format changes;
- export template/platform requirements.

The project must remain loadable by 4.6.3 until an ADR explicitly approves a
new engine line.
