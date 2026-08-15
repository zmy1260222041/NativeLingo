# R-15 · Godot Web Beta 无语音内测发布符合性评审（2026-08-15）

> 需求来源：用户提供的《Godot 网页内测发布方案》（下文称 W1..W5）。
> 本评审只覆盖 `game/`（Stranger 竖切片）的 Web 导出与无语音改造，以及
> 托管/访问控制的**可提交配置与脚本**；域名注册、ICP 备案、服务器购买、
> 腾讯问卷创建属于用户外部操作，不在代码评审范围。

## 1. 需求-实现追踪

| 编号 | 需求 | 实现位置 | 结论 |
|---|---|---|---|
| W1 | Godot 4.6.3 Web export templates + `Web Beta` 导出预设（Compatibility、无 Threads、无 PWA、feature `web_beta_no_voice`、输出 `build/web/`、排除测试/工具/开发文件、构建脚本） | `game/export_presets.cfg`、`scripts/build_stranger_web_beta.sh` | ✅ |
| W2 | `SpeechAdapter.is_available()`；无语音构建不录音、不创建麦克风/HTTP；网页忽略说话键；隐藏语音模式与“说话”重映射；NPC 提示改为手势/观察；显示无语音说明 | `game/scripts/speech_adapter.gd`、`player_controller.gd`、`interactable.gd`、`hud.gd`、`input_remap_panel.gd`、`scenes/ui/HUD.tscn`、`localization/stranger.csv` | ✅ |
| W3 | Web 构建禁用 AnimationDebugBridge 的 TCP/WebSocket、30 Hz 采样、日志写入 | `game/scripts/animation_debug_bridge.gd`（`OS.has_feature("web")` 短路；addon 类改运行时 `load` 以支持导出排除） | ✅ |
| W4 | 暂停/通关页问卷入口；构建标签 `web-beta.1`；浏览器 `user://` 存档与清除提示 | `project.godot [web_beta]`、`hud.gd`、`HUD.tscn`、本地化 | ✅（问卷 URL 由用户创建后回填） |
| W5 | Nginx 80/443、Basic Auth bcrypt 白名单、TLS 自动续期、WASM MIME、静态预压缩、首页禁缓存、安全头、发布目录/回滚、日志 30 天、无 CI 部署 | `production/web-beta/`（`nginx-site.conf.template`、`accounts.sh`、`setup_server.sh`、`deploy.sh`、`rollback.sh`、`validate.sh`、`README.md`） | ✅ 配置就绪，服务器/域名就绪后可执行 |

## 2. 实测结果（2026-08-15，第二轮）

- Godot 版本校验：`4.6.3.stable.official.7d41c59c4` ✅
- 测试（`scripts/build_stranger_web_beta.sh` 内全绿）：`test_game_state.gd`、
  `HudTest.tscn`、`WebBetaNoVoiceTest.tscn`（14 项全绿）、
  `VoiceTargetCancelTest.tscn`、`MainEnvIntegration.tscn`、`test_walk_fix.gd`、
  `test_directional_locomotion.gd`。
- Web Beta Release 导出成功；PCK 目录条目 248 个，`res://tests|tools|addons|speech_service`
  均为 0 ✅。
- gzip -9 预压缩后首包 `index.wasm.gz + index.pck.gz + index.js.gz` = **35.0 MiB**，
  低于 70 MiB 门槛 ✅；`SHA256SUMS` + `build-info.json` 已生成。
- 无语音模式行为由 `WebBetaNoVoiceTest` 锁定：不录音、不冻结时间、无 HTTPRequest、
  说话键忽略、重映射 14 行、NPC 提示只含手势/观察、手势可完成三日流程。
- **真实 Web Release 浏览器冒烟**（Playwright/Chromium，本地正确 MIME + gzip 服务）：
  - headless：canvas 1440×900 初始化成功，mic API 调用 0，localhost/语音请求 0，
    控制台错误 0，页面错误 0 ✅；
  - `WEB_BETA_HEADED=1`：额外验证首次点击后指针锁定成功、页面错误 0 ✅。
  - 指针锁修复：`PlayerController` 在 Web 构建不再于启动时请求捕获；
    `production/web-beta/web_shell_patch.js` 在导出后注入 HTML，把请求放在真实
    `mousedown` 手势内，并吞掉 Godot 忽略返回值的 Promise rejection。

## 3. 边界与残留项

- 双平台/双浏览器（Windows/macOS × Chrome/Edge）、1366×768/1440×900 手动通关、
  存档刷新/清除重置，仍需服务器上线后在真实域名按 `production/web-beta/README.md` §6 执行。
- `VoiceTargetCancelTest` 已修复并通过：原先测试沿 Y 轴移出，但交互距离按 XZ
  平面计算，现已改为水平移出。
- `MainEnvIntegration` 已修复并通过：`DayCycleLighting.Look.fog` 缺省改为冷雾
  `cde3f2`（此前为暖白色），heater 期望位置更新到当前 v03 摆位。
- 备案号展示：ICP 备案通过后需在页面底部注入（Nginx `sub_filter` 或自定义 HTML shell）。
- 问卷 URL：`project.godot [web_beta] survey_url` 当前为空，按钮隐藏；填 URL 后重建即可出现。
