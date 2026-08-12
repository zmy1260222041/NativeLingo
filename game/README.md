# 异乡人 / Stranger — Vertical Slice

A standalone Godot 4.6 third-person social-survival RPG prototype.

## Run

```sh
/Applications/Godot-4.6.app/Contents/MacOS/Godot --path game
```

Or import `game/project.godot` in Godot 4.6.3 and press **F6/F5**.

## Controls

- `WASD` / left stick: move
- Mouse / right stick: orbit camera
- `Shift` / left-stick click: sprint
- `Space` / gamepad south: jump
- `E` / gamepad west: physical interaction
- Hold `V` / left shoulder: record a key English interaction; release to send
- `G` / gamepad north: gesture fallback and free retry path
- `Esc` / Menu: pause; `Esc` / gamepad east cancels speech and closes modals
- `F9`: reset the three-day prototype and its save

Hold-to-talk can be changed to toggle-to-talk from the pause menu. The same menu
provides reduced motion, 80–150% HUD scaling, and keyboard/gamepad remapping for
all core movement, camera, interaction, speech, and menu actions. Binding
conflicts require confirmation and can be restored to the project defaults.

## Current playable path

1. Day 1: greet Mira, gather two berries, sleep at the shelter.
2. Day 2: gather two alloy parts, repair the heater, sleep.
3. Day 3: take water to Rowan and communicate by voice intent or gesture.

The prototype uses five distinct procedural NPC silhouettes, contextual character
acting, and a responsive bilingual HUD. The player runtime mesh is intentionally
absent until the Rodin-derived character passes Gate D. For
offline voice recognition, start `game/speech_service/server.py` as described in
its README.
Pressing `G` always provides the non-punitive physical confirmation required by
the design, including when microphone permission or the service is unavailable.
The bundled Noto Sans SC variable font is licensed under the SIL Open Font
License; its license text is stored beside the font in `game/assets/fonts/`.

## Tests

```sh
/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game --script res://tests/test_game_state.gd

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/HudTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/VoiceTargetCancelTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game --script res://tests/test_character_asset.gd

python3 -m py_compile game/speech_service/server.py
```

## Build the player character source

The only valid character source pipeline begins with the Rodin delivery and a clean
Blender import:

```sh
/Applications/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup \
  --python art/source/characters/chr_player_juvenile/blender/import_render_rodin_v04.py
```

Continue only with
`art/source/characters/chr_player_juvenile/source_locked_v04/RODIN_PRODUCTION_PIPELINE.md`.
The runtime GLB is exported only after Gate D; current evidence is recorded in
`design/assets/player-juvenile-validation.md`.
