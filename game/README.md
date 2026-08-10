# 异乡人 / Stranger — Vertical Slice

A standalone Godot 4.6 third-person social-survival RPG prototype.

## Run

```sh
/Applications/Godot-4.6.app/Contents/MacOS/Godot --path game
```

Or import `game/project.godot` in Godot 4.6.3 and press **F6/F5**.

## Controls

- `WASD` / left stick: move
- Mouse: orbit camera
- `Shift` / left-stick click: sprint
- `Space` / gamepad south: jump
- `E` / gamepad west: physical interaction
- Hold `V` / left shoulder: record a key English interaction; release to send
- `G` / gamepad north: gesture fallback and free retry path
- `Esc`: release/capture mouse
- `F9`: reset the three-day prototype and its save

## Current playable path

1. Day 1: greet Mira, gather two berries, sleep at the shelter.
2. Day 2: gather two alloy parts, repair the heater, sleep.
3. Day 3: take water to Rowan and communicate by voice intent or gesture.

The prototype uses original procedural placeholder geometry. For offline voice
recognition, start `game/speech_service/server.py` as described in its README.
Pressing `G` always provides the non-punitive physical confirmation required by
the design, including when microphone permission or the service is unavailable.

## Tests

```sh
/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game --script res://tests/test_game_state.gd
```
