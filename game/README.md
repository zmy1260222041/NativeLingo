# Stranger · 2D 对话与养成分支

本分支默认进入 `scenes/Novel.tscn`。六个地点、五名 NPC 立绘、逐字对话与双人小剧场、成长/词汇、行囊/柜台/住处、回看和设置构成新的游戏界面。原 3D 场景保留为历史参考。

```sh
/Applications/Godot-4.6.app/Contents/MacOS/Godot --path game
```

推荐双击 `game/run_novel.command`：自动启动本地语音服务，再打开游戏。服务保持运行供下次使用，日志在系统临时目录的 `stranger-novel-speech.log`。也可在语音服务已经运行时打开 `build/novel/Stranger2D.app`。专用导出预设为 **macOS 2D Novel**，只携带 2D 运行依赖、角色卡与词表，不包含 3D 模型。

- 点左侧地点，或按 1–6 切换；E 交谈，V 开始/结束录音，G 手势，B 行囊，Esc 设置/返回。
- Tab / 方向键选择按钮，Enter 或手柄 A 确认；原 InputMap 的交谈、手势、录音也可用。手柄通过界面地点按钮切换场景。
- 语音不可用时，手势领取最低份量；语音可用时，仍需通过原有具名成交规则取得物品。柜台领取后可以现场使用或打包。
- 成长页选择单词→听美国语音示范（可重听）→V 录音、再按 V 结束→得到发音反馈→在商店自然交谈中使用。播放示范时禁止录音，低分可免费重试。小剧场听九段四句日常对白，包含打包点餐、选饮品、买电池、借毯子和邻里往来；开口灵感按当前地点提供示例，仍需自己录音交流。在住处安放/安装物品，休息到夜晚，然后睡觉；度过三夜结束。
- 行囊 / 柜台 / 住处支持分类与合并数量，详情显示来源、剩余次数、用途和当前实际恢复量；主要操作具名回执，满状态不消耗，浪费需确认。柜台提示待取数量，支持全部打包；空行囊可直接前往补给点。
- 读文字、对话与练习不扣需求，只有明确行动推进时间。住处休息有较低需求消耗。
- 首次启动读取已有 `stranger_save.json`，后续写入独立 `stranger_novel_save.json`。不会覆盖 3D 存档。设置可存读档、减少动态、调整对话字号、切换逐字显示、重映射键鼠/手柄动作和确认重开。
- 本分支默认使用 xAI 美国 us-east-1 TTS（服务端已有 `XAI.csv` / `XAI_API_KEY`），Gemini 负责自然对话。设置中可重新检查连接；模型失败不会用脚本模拟评分或成交。历史 Qwen 配置仅供显式设置 `STRANGER_TTS_PROVIDER=qwen` 的旧版调试，默认不连接北京端点。

验证：

```sh
/Applications/Godot-4.6.app/Contents/MacOS/Godot --headless --path game res://tests/NovelTest.tscn
# 行囊、日常对白、焦点、真实鼠标遮挡与小尺寸渲染
/Applications/Godot-4.6.app/Contents/MacOS/Godot --path game res://tests/NovelEverydayTest.tscn -- --everyday-capture
# 真实生活情景对话与新台词美国 TTS（文字测试输入）
.venv/bin/python game/speech_service/probe_everyday.py
# 同时生成桌面截图（测试使用独立状态，不读取用户存档）
/Applications/Godot-4.6.app/Contents/MacOS/Godot --path game res://tests/NovelTest.tscn -- --novel-capture
# 真实 API + 游戏录音通道 + 多轮交谈 + 物资和词汇闭环（合成输入，不采集真人麦克风）
.venv/bin/python game/speech_service/probe_novel_live.py
# 本地导出
/Applications/Godot-4.6.app/Contents/MacOS/Godot --headless --path game --export-release "macOS 2D Novel" ../build/novel/Stranger2D.app
```

界面配色统一为暖纸白、燕麦灰、鼠尾草绿和少量黄铜棕，涵盖对话、物品、提示与按键设置。配色与对比度验收：`docs/reviews/2026-09-11-soft-palette-fit.md`。

字体与边框采用视觉小说的阅读层级：Noto Serif SC 宋体用于对白、姓名牌和标题，Noto Sans SC 常规字重用于操作与状态；细分隔线、轻选中标记和小圆角减少框线干扰。录音固定在对话操作区右侧；逐字出现时可点「显示全文」，小剧场先补全本句、再推进下一句，末句返回现场。大字号容纳三行中文，更长回应可滚动阅读，新回应回到顶部。字体与许可随包提供。验收：`docs/reviews/2026-09-11-novel-typography-fit.md`。

2026-09-11 试玩优化：小剧场保持角色站位；单词练习使用独立操作区与常驻提示；住处根据入睡条件提供休息或入睡主操作；词汇阶段改为中文名称；首次引导简化为点餐三步，完整帮助保留在设置中。见 `docs/reviews/2026-09-11-ux-followup.md`。

行囊与生活化体验验收：`docs/reviews/2026-09-11-everyday-inventory-fit.md`（R-36 / FR-47）。

迁移矩阵和证据：`docs/reviews/2026-09-11-stranger-2d-dialogue-fit.md`（R-34 / FR-46）。美国 TTS 与口语闭环证据见 `docs/reviews/2026-09-11-stranger-2d-speaking-fit.md`（R-35）。

---

以下为原 3D 版本及共享语音/领域模块的历史运行说明；移动、跳跃和场景快捷键不适用于本分支默认入口。

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
- Hold `Tab` / right shoulder: carried items (pause settings also offer toggle mode)
- In item selector: arrows / D-pad up-down select; `E` / west uses or places; `R` / D-pad right packs or reclaims; `T` / D-pad left packs all counter items
- Hold `V` / left shoulder: record a key English interaction; release to send
- `G` / gamepad north: gesture fallback and free retry path
- `Esc` / Menu: pause; `Esc` / gamepad east cancels speech and closes modals
- `F9`: reset the three-day prototype and its save

Hold-to-talk can be changed to toggle-to-talk from the pause menu. The same menu
provides reduced motion, 80–150% HUD scaling, and keyboard/gamepad remapping for
all core movement, camera, interaction, speech, and menu actions. Binding
conflicts require confirmation and can be restored to the project defaults.

## Current playable path

There is **no assigned quest order** (FR-42). Needs decide where to go:

- Hungry → a shop that serves food (Tavi's counter).
- Thirsty / low energy → the convenience store (Ori).
- Night or worn out → sleep at the shelter.

Resources still come from **finished service conversations** (FR-41 + FR-28).
Talk in English; the session score is half pronunciation and half how
idiomatic the lines were. Completing the order grants a banded reward.
Walking away or scoring below 40 grants nothing and can be retried.

FR-44: completed orders now put concrete items on the customer-side tray, not straight into needs or a backpack.
Walk up and press `E`: eat/drink one on site or pack it for later. Only explicit use restores that item's own needs.
Carry capacity is 4 food/drink slots and 1 household slot, with compatible stacks of 2 (canteens occupy one slot each).
Blankets, batteries and heater parts must be carried to the home bed, power station or workbench, placed, then used in a second action.
The current shelter has no walkable interior, so these named positions are in its exterior living area; sleep has a separate entrance interaction.
The home chest can store carried items and holds overflow migrated from old saves. Save v5 preserves instances and transaction IDs.
Vocabulary observation/practice/later spoken usage remains asynchronous and independent: no item event grants vocabulary progress.
See [item rules](../design/gdd/item-usage.md) and [implementation evidence](../docs/reviews/2026-09-06-item-usage-fit.md).

The three days are only a time box: last three nights and the slice ends.
Repairing the heater and bringing water to Rowan are optional and do not
gate sleep or completion.

Forage tokens and the reservoir are guidance objects now; they no longer grant
resources. When speech is unavailable (no-voice builds, missing microphone, or
no local service), the `G` gesture fallback grants the minimum survival
portions so three nights stay fully playable.

A first-run guide protects the three needs while teaching movement, a voiced
greeting, and a voiced food request. Explicit gesture fallback replaces either
spoken beat only when the runtime confirms speech is unavailable. The graded vocabulary profile defaults to
toddler (A1+A2) and is built at runtime from the unchanged CEFR-J, Octanove,
and NGSL assets under `assets/wordlists/`; see `ATTRIBUTION.md` there for the
two distinct licences.

NPC dialogue is **voice only**: greetings, social scenes, and NPC replies are
spoken through the server-side TTS catalog (Qwen `qwen-audio-3.0-tts-plus`
over the DashScope WebSocket route; each NPC has a fixed system voice). Text
toasts appear only in builds where the voice channel itself is unavailable
(unactivated cloud-voice / no-voice betas) plus for mechanical feedback
(rewards granted, heater repaired, and similar system narration).
NPC voice is emitted from the speaking character in 3D, attenuates with
distance, and is deliberately quieter than the former global UI-like playback.

## Service-point NPC dialogue (FR-41)

Walk up to a service point when you need something and talk:

- Tavi — food-counter server at the market stall (`env_market_stall_a`). Order anything on the board (burger, coffee, sandwich).
- Ori — convenience-store cashier. Buy water or other counter items. The store building is not in yet; she still stands by the reservoir.
- Mira — market greeter beside the stall. She does not take orders.
- Vesh — optional hardware clerk. Not on the main need path.
- Rowan — resident neighbor. Not a shopkeeper.

The player speaks first. The local (or cloud) service sends the transcript,
role card, and recent turns to Gemini (`gemini-3.1-flash-lite` with
`thinking_level=MINIMAL` over `streamGenerateContent`). Pressing `V` warms the
shared Gemini HTTPS session, a tiny throttled streamed model probe, and the TTS
websocket while the player records.
The live plane races identical short-window Flash-Lite requests to absorb an
occasional slow upstream connection; only a safe, request-relevant model utterance
can win. A normal turn starts audio on the first safe sentence. A settlement turn may
wait for the second short sentence when the first is only a generic acknowledgement,
so the committed audio explicitly names the item and the handoff before it can close.
Idiomaticity / transaction JSON may
arrive after the mouth is already open. A deterministic stub remains an outage
and offline recovery path, but a configured, prewarmed online latency acceptance
run must report `source=gemini`, never `source=stub`. Session score is `0.5 × pronunciation + 0.5 ×
idiomaticity`. Resources are granted only after the spoken reply names a concrete
scenario-inventory item, contains a non-question handoff commitment, uses a completion
speech act, and that same reply's audio has finished. Generic `Sure thing.` / category
questions never settle even if a model completion flag claims otherwise. The server,
Godot dialogue service, scenario runner, and GameState each enforce this boundary,
using the same FR-28 bands as before. Walking away grants nothing. `G`
remains goodwill only, or `gesture_fallback` when speech itself is
unavailable.

The Godot client never holds a Gemini or xAI key and never sends free text
to TTS. NPC replies are spoken through a server-issued `reply_id`. Without
`GEMINI_API_KEY` / `GEMINI.csv`, the service may use Grok if an xAI key is
present; otherwise a deterministic stub keeps tests and offline integration
running. YouTube discovery tools stay in `game/speech_service/` as optional
research; they do not feed these counters.

With the localhost service already running, the opt-in desktop SSE acceptance
probe (it briefly opens a Godot window) is:

```bash
/Applications/Godot-4.6.app/Contents/MacOS/Godot --path game \
  --script res://tests/test_live_npc_dialogue.gd
```

NPCs periodically meet for ambient need-expression scenes: the two family or
partner NPCs **walk to a meeting point near each other**, exchange the lines
as voice, and stroll back to their spots afterwards. A scene is skipped when
the player is talking to one of the participants, and no gathering happens
while the onboarding guide is active (the guide's target NPC stays put).
The scripts are deliberately reviewed text server-side so a coverage test
can prove each survival-essential expression (greeting, food, alloy parts,
water, offering help) is observable.

New words move through heard → spoken → used. During social dialogue an NPC
may ask by voice "Do you want xx, yy, or zz?"; the player holds V and says the
chosen word. The server matches the spoken choice and scores it through the
independent `POST /score_word` protocol (local dev or cloud). The first
successful spoken unlock opens a spelling card.

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
  --headless --path game --script res://tests/test_onboarding.gd

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/NpcAttentionTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/NpcVoiceTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/VocabularyTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/SocialDialogueTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game --script res://tests/test_npc_dialogue_assets.gd

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/WordAcquisitionTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/WordPracticeTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/GuidedWordPracticeTest.tscn

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game --script res://tests/test_voice_gated_rewards.gd

/Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/CloudVoiceTest.tscn

# Live cloud activation + cloud TTS smoke (needs a fresh one-time code from
# the server: `cd /opt/nativelingo && .venv/bin/python -m backend.core.devices code`).
NL_TEST_CODE=<code> /Applications/Godot-4.6.app/Contents/MacOS/Godot \
  --headless --path game res://tests/CloudActivationLiveTest.tscn

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
python3 -m unittest \
  game.speech_service.test_dialogue \
  game.speech_service.test_corpus_pipeline \
  game.speech_service.test_native_speaker_screener -v
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
`game/speech_service/reference_audio/`. The local NPC TTS reads its Qwen
credentials from `game/speech_service/TTS.csv` (operator-provided, git
ignored) — see that service's README for the DashScope SDK dependency and
the per-NPC system voices.

Export note (2026-08-17): the cloud-voice presets carry
`include_filter="*.pem"` so the pinned CA actually lands in the PCK —
`.pem` is not a recognized Godot resource and is silently dropped otherwise.
Two export-only TLS bugs were fixed alongside: the CA is now loaded via
`FileAccess.file_exists` + `X509Certificate.load` (`ResourceLoader.exists`
is always false for non-resource files in exports, which broke activation),
and `NpcVoice` configures the pinned CA on its own HTTPRequest (previously
only `SpeechAdapter` did, which broke every cloud TTS request).

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
