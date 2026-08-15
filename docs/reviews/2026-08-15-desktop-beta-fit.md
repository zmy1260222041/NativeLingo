# R-16 · Stranger Desktop Beta 无语音分发符合性评审（2026-08-15）

> 需求来源：用户已确认的《Stranger 桌面版交付计划》D1–D4，以及
> `docs/stranger-desktop-delivery-plan.md`。
> 评审范围：`game/` 桌面导出改造、`scripts/build_stranger_desktop.sh`、
> `production/desktop/` 发布工具与真机验收清单；GitHub Release 实际发布
> 与 macOS Developer ID 公证证书属于外部操作，不在本代码评审内。

## 1. 决策-实现追踪

| 决策 | 需求 | 实现 | 结论 |
|---|---|---|---|
| D1 | 首版无语音，手势完成全部 NPC 交互 | `SpeechAdapter.is_available()` 增加 `desktop_beta_no_voice`；HUD/输入重映射复用同一门控；`DesktopBetaNoVoiceTest` | ✅ |
| D2 | GitHub Releases 分发 | `production/desktop/publish_github_release.sh`、`release_notes.md`（仓库公开，可匿名下载） | ✅ 脚本就绪，实际发布待 gh auth 与问卷链接 |
| D3 | macOS Developer ID + 公证；Windows 免签 | 构建脚本支持 `MACOS_SIGN_IDENTITY` + notarytool/staple；未配置时 ad-hoc 签名；release notes 写明 SmartScreen | ✅（证书到位后即可启用） |
| D4 | macOS Apple Silicon + Windows x64 | `Windows Desktop Beta`（x86_64）、`macOS Desktop Beta`（导出 universal 后 `lipo -thin arm64`） | ✅ |

## 2. 实现内容

- `game/export_presets.cfg`：新增 Windows Desktop Beta 与 macOS Desktop Beta
  预设，均带 `desktop_beta_no_voice`，排除 `tests/tools/addons/speech_service`。
- `project.godot`：新增 `[desktop_beta] build_label/survey_url`；开启
  `textures/vram_compression/import_etc2_astc=true`（macOS arm64 导出要求）。
- `hud.gd`：Web/Desktop 两套 beta 文案与构建标签分流；`DESKTOP_NO_VOICE_NOTICE` /
  `DESKTOP_SAVE_NOTE` 本地化。
- `animation_debug_bridge.gd`：桌面 beta 分发包同样禁用 6505/6506/6507、
  30 Hz 采样与 `user://logs` 写入。
- `tests/DesktopBetaNoVoiceTest.tscn` + `test_desktop_beta_no_voice.gd`：16 项断言。
- `scripts/build_stranger_desktop.sh`：版本校验、导入、8 套测试、双平台导出、
  macOS PCK 审计、lipo 瘦身、签名/公证、Windows ZIP、macOS DMG、SHA-256、
  build-info、300 MiB 包体门槛。
- `production/desktop/`：发布脚本、下载说明、真机验收清单。

## 3. 实测结果（2026-08-15）

- 8 套 Godot 测试全绿：`game_state`、`HUD`、`WebBetaNoVoice`、
  `DesktopBetaNoVoice`（16/16）、`VoiceTargetCancel`、`MainEnvIntegration`、
  `walk_fix`、`directional_locomotion`。
- Windows export：`stranger.exe` 148 MiB；ZIP **60.5 MiB** ≤ 300 MiB。
- macOS export：universal 模板瘦身后 arm64，DMG **58.2 MiB** ≤ 300 MiB。
- macOS PCK 248 个条目中 `res://tests|tools|addons|speech_service` 均为 0。
- 导出后的 macOS 二进制以 `--headless --quit-after 5` 启动，退出码 0，
  无引擎启动崩溃。
- `build/desktop/SHA256SUMS.txt` 与 `build-info.json` 已生成。
- 当前 macOS 包为 **ad-hoc 签名**（未提供 Developer ID），发布前需按 D3
  补公证，或在 release notes 明确右键打开路径。

## 4. 残留项与发布门槛

- Windows 真机未在本机执行：需在 Windows 10/11 x64 上按
  `production/desktop/acceptance-checklist.md` 完成 B 组。
- macOS GUI 真机通关/输入/HUD/存档矩阵（C 组）需人工执行。
- 问卷 URL 待回填：`game/project.godot [desktop_beta] survey_url`。
- GitHub release 实际创建待 `gh` 认证与人工复核。
- 应用图标：当前沿用 Godot 默认图标，正式发布前需提供 Stranger 图标源图。
