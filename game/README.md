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

Resources now come from **voiced English requests judged by the NPC** (FR-28):
the clearer the pronunciation and the meaning, the more the NPC gives; a weak
expression gives nothing but costs no opportunity and can be retried freely.

1. Day 1: greet Mira, ask Tavi for two portions of food by voice, sleep at the shelter.
2. Day 2: ask Vesh for two alloy parts by voice, repair the heater, sleep.
3. Day 3: ask Ori for water by voice, take it to Rowan and express your offer.

Forage tokens and the reservoir are guidance objects now; they no longer grant
resources. When speech is unavailable (no-voice builds, missing microphone, or
no local service), the `G` gesture fallback grants the minimum survival
portions so the three-day path stays fully playable.

The prototype uses five distinct procedural NPC silhouettes, contextual character
acting, and a responsive bilingual HUD. The player runtime uses the
`chr_player_juvenile_mixamo.fbx` package: the same-mesh Mixamo actions are
direction-and-twist retargeted offline, then selected at runtime as standing idle,
walk, run, pointing, environment observation, gathering, 180-degree turn, or jump.
Berry/scrap/water world objects still play `anim_chr_player_interact_gather`
but are guidance props now — they only point you to the NPC supplier; fixed
facilities (heater and shelter) use `anim_chr_player_interact_observe`; NPCs
retain their social reactions. The source Mixamo T-pose and the skinned game
rig's arms-down rest pose are intentionally not treated as interchangeable.
For offline voice recognition in **dev mode**, start
`game/speech_service/server.py` as described in its README; cloud-voice builds
do not need it. Pressing `G` is the non-punitive physical confirmation path:
with speech available it grants nothing, and when speech is unavailable or
unactivated it becomes `gesture_fallback` and grants the minimum survival
portions so the mainline stays completable.
The bundled Noto Sans SC variable font is licensed under the SIL Open Font
License; its license text is stored beside the font in `game/assets/fonts/`.

## Tests

```sh
/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game --script res://tests/test_game_state.gd

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game --script res://tests/test_voice_gated_rewards.gd

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/CloudVoiceTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/HudTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/VoiceTargetCancelTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/WebBetaNoVoiceTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game --script res://tests/test_character_asset.gd

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game --script res://tests/test_walk_fix.gd

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game --script res://tests/test_directional_locomotion.gd

python3 -m py_compile game/speech_service/server.py
```

## Web Beta build

The first web beta ships without voice: `web_beta_no_voice` disables
`SpeechAdapter`, removes every speech UI entry, and leaves the three-day flow
fully playable through `G` gestures. (Voice-enabled web/desktop beta builds
now use the `Web Cloud Voice` preset — see the next section.) The reproducible
no-voice build runs the test suites, exports the `Web Beta` preset,
precompresses the payload, and writes `SHA256SUMS` + `build-info.json`:

```sh
scripts/build_stranger_web_beta.sh
```

Deployment/access-control tooling and the launch checklist live in
`production/web-beta/`.

## Cloud voice scoring (FR-29)

Cloud-voice builds (`stranger_cloud_voice` export presets) upload each spoken
request to the self-hosted scoring server instead of running local models:

- Desktop presets pin the private CA shipped as `res://certs/nl_ca.pem`
  (operator-injected at build time, never committed). macOS preset has
  `audio_input=true`.
- Web preset uses same-origin `/game/evaluate` through the nginx `location
  /game/` proxy, so there is no CORS or private CA in the browser.
- First run: pause menu → *Activate Cloud Scoring* → enter the operator's
  one-time code (`POST /register` exchanges it for a per-device token stored
  in `user://`). No credential is baked into the PCK.
- Unactivated, offline, or 5xx scoring falls back to the `G` gesture minimum
  path, so the three-day mainline stays playable (NFR-7 / FR-29).

Dev mode is unchanged: `stranger_cloud/enabled=false` keeps the local optional
service (`game/speech_service/server.py`) and its bundled reference WAVs in
`game/speech_service/reference_audio/`.

## Build the player character source

The player source pipeline uses the Tencent Hunyuan3D Pro base and a clean
Blender import:

```sh
/Applications/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup \
  --python art/source/characters/chr_player_juvenile/blender/import_render_hunyuan_v05.py
```

Continue only with
`art/source/characters/chr_player_juvenile/source_locked_v05/HUNYUAN_FROM_CONCEPT_RUNBOOK.md`.
The runtime GLB is exported only after Gate D; current evidence is recorded in
`art/source/characters/chr_player_juvenile/source_locked_v06/README.md`.

## Player animation scale safeguard

The Blender FBX exporter can add an `Armature` scale track to baked actions.
Because FBX centimeter conversion is read by Godot as `(100, 100, 100)`, the
player previously popped to a much larger size when Walk or the `G` gesture
started. `retarget_mixamo_actions.py` keeps bone rotation plus valid in-place Hips
motion while dropping unsafe object transforms and bone scale; because Blender's FBX
bake may still materialize a unit-conversion track,
`CharacterVisual._sanitize_runtime_animation_tracks()` removes imported Armature-object
position and all scale tracks defensively after Godot import. Player translation remains owned by
`PlayerController`/`CharacterBody3D`. `tests/test_walk_fix.gd` fails if walk, run,
pointing, Observe, Gather, Turn 180, or Jump contains scale or non-Hips position, or
if the authored actions lose dynamic Hips motion.

The final runtime rule is narrower: Armature object transforms and every scale track are
removed, while authored Hips bounce/weight-shift motion is restored from
`assets/characters/chr_player_juvenile_mixamo_retarget.json` as a
`Armature/Skeleton3D:Hips` position track. Hips motion is in-place; world movement remains
owned by `PlayerController`.

The retargeter evaluates `local_delta`, the legacy `world_rest`, and
`pose_direction`. Selection is based on authored source bone directions and actual solved
target poses, not on a formula compared against itself. The runtime report at
`assets/characters/chr_player_juvenile_mixamo_retarget.json` records per-bone direction
error, rotation error, endpoint error, Hips motion, and the selected algorithm.
`tests/test_walk_fix.gd` also probes hand, knee, and foot global positions at four walk
phases so crossed/folded limbs fail automatically.

## Directional locomotion, Turn 180, and Jump

`CharacterBody3D` yaw belongs to the third-person camera; the visible character now keeps
an independent world-facing direction. Walk/Run always face the planar movement vector.
Direction changes below 135 degrees steer continuously at 360 degrees/second, with the
planar velocity rotating through the same bounded step. Changes at or above 135 degrees
stop planar motion and play `anim_chr_player_turn_180`. The clip always finishes an exact
authored reversal; any residual angle in a near-opposite request is then completed by the
continuous steering path.

Turn completion samples 64 phases of Walk/Run against the Turn endpoint using both feet
and toe bones. The selected Walk phase currently has about 29 mm raw mean offset. A
whole-model translation correction reduces the switch-frame foot residual to about
0.1 mm and decays over 0.2 seconds. Held sprint still exits through this matched Walk
phase before blending to Run; this avoids the much poorer direct Turn-to-Run contact.

`anim_chr_player_jump` is split at offline-measured foot contacts. A 2%-of-height clearance
threshold sustained for three frames finds takeoff at source frame 40 (`1.300s`) and
landing at frame 59 (`1.933s`). Pressing Jump starts the crouch anticipation at 1.6x;
`PlayerController` applies its vertical impulse only at frame 40. The airborne animation
segment is scaled to physical airtime, and floor contact starts recovery at 1.25x from
frame 59. The report's authored post-takeoff Hips lift (`0.09534548m`) is subtracted from
the desired ballistic height before calculating the impulse, so animation and physics do
not double the jump height. `tests/test_directional_locomotion.gd` locks the steering,
turn phase handoff, marker timing, and recovery states.

Jump input has a `0.2s` landing buffer. If another Jump is pressed just before or just
after contact, runtime samples 40 anticipation poses, selects the closest full-body/foot
phase, and crossfades from recovery for `0.18s`. It alternates an internal duplicate of
the same source Jump action so `AnimationPlayer` performs a real blend instead of
resuming the same animation name. Telemetry reports `jump_chain_entry_time`, pose and
rotation error, and `jump_chain_count`.

Gestures are locked for the complete Jump sequence. Previously an airborne `G` replaced
Jump with Point while `jump_active` remained true; landing then sought the Point clip and
the animation state never returned to locomotion. Both `PlayerController` and
`CharacterVisual` now reject that transition, log `gesture_rejected`, and a defensive
jump-animation guard repairs any foreign one-shot before takeoff/landing processing.

## Animation debugging ports

When the game is running, `AnimationDebugBridge` exposes localhost WebSocket JSON-RPC:

- `6505`: input, game control, screenshots, freeze and `control.animation_probe`.
- `6506`: `log.tail`, `log.subscribe`, `animation.get_state`, and frame telemetry,
  including per-bone local, skeleton-global, and world position/rotation plus jump-stage
  and turn-phase-match diagnostics.
- `6507`: `test.list`, `test.write_inline`, `test.run`, and `test.result`.

The telemetry stream is stored in `user://logs/animation_telemetry.jsonl`; the regular
debug log is `user://logs/debug.log`. The editor plugin owns these ports only while no game
is running and releases them when the play session starts.
Animation probes force the skinned LOD0 and reject external reactions until the probe ends.
Captured probe JPEGs are written to `user://logs/animation_probe/`; RPC responses return
their numbered paths instead of embedding large Base64 payloads. Use `animation.sample` on
6506 when an explicit live bone set is required.
`input.simulate_key` and key events inside `input.simulate_sequence` set both logical and
physical keycodes, matching this project's physical-key InputMap.
